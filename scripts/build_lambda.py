#!/usr/bin/env python
"""Lambda（python3.12 / x86_64 / Amazon Linux 2023）用のデプロイパッケージを作る。plan §7.4。

使い方（リポジトリのルートで）:
    python scripts/build_lambda.py

- 依存（backend/requirements.txt）は、Linux 用の wheel だけを PyPI から入れる
  （`--platform` を 3 つ・`--implementation cp --python-version 3.12 --only-binary=:all:`）。
  Windows の site-packages は使わない。pip は backend/.venv の Python のものを使う。
  - `--platform` に `manylinux_2_28_x86_64` だけを指定すると、pip 26.3 は古いタグ
    （`manylinux_2_17` / `manylinux2014`）の wheel を候補にせず、pydantic-core が見つからなかった
    （2026-11-25 に実測）。そこで 3 つのタグを並べる。
    manylinux のタグは「その glibc 以上で動く」ことを表し、
    Amazon Linux 2023 の glibc はそれより新しい。
    最終確認は Lambda 上での import で行う（docs/deploy.md）。
- 間接依存（starlette・anyio など）の版は、テストを実行した backend/.venv の `pip freeze` を
  制約（`-c`）として渡して固定する。Lambda には、テストで使ったものと同じ版が入る。
- アプリは backend/main.py と backend/app/*.py だけを入れる
  （tests/・tools/・__pycache__ は入れない）。
  pip が作るコマンドの起動用ファイル（bin/。Windows では .exe）も入れない。
- 出力：build/lambda.zip と build/lambda-report.json
  （wheel のタグ・ネイティブ拡張の一覧・サイズ・SHA-256）。
  build/ は Git 管理の対象外。実行のたびに build/lambda/ を作り直す（build/ の外は消さない）。
- 次のどれかに当てはまれば、zip を作らずに終了コード 1 で止める：
  - Windows・macOS 用のバイナリ（.pyd・.dll・.dylib）が入った
  - ネイティブ拡張（.so）の wheel のタグが cp312・manylinux・x86_64 でない
  - サイズの上限（zip 50 MB・展開後 250 MB）を超えた
- AWS には接続しない。アップロードは docs/deploy.md の手順で、承認を得てから行う。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
BUILD = ROOT / "build"
STAGE = BUILD / "lambda"
ZIP_PATH = BUILD / "lambda.zip"
REPORT_PATH = BUILD / "lambda-report.json"

PLATFORMS = ("manylinux_2_28_x86_64", "manylinux_2_17_x86_64", "manylinux2014_x86_64")
CONSTRAINTS_PATH = BUILD / "lambda-constraints.txt"
PYTHON_VERSION = "3.12"
ZIP_LIMIT = 50 * 1024 * 1024  # 直接アップロードの上限
UNZIPPED_LIMIT = 250 * 1024 * 1024
FOREIGN_BINARY_SUFFIXES = (".pyd", ".dll", ".dylib", ".exe")
# zip に入れない（キャッシュ・テスト・手動の確認用ツール）
EXCLUDED_DIRS = {"__pycache__", "tests", "tools", ".venv"}
FIXED_DATE = (2026, 1, 1, 0, 0, 0)  # zip の中の日時を固定し、同じ入力から同じ zip を作る
# Amazon Linux 2023（python3.12 のランタイム）の glibc の版。
# .so がこれより新しい版を要求したら止める（最終確認は Lambda 上での import）
RUNTIME_GLIBC = (2, 34)
# Windows でビルドしたときに混入しうる Windows 専用の依存。
# pip の --platform を使っても、環境マーカー（sys_platform など）は実行しているホストで評価される
WINDOWS_ONLY_DISTS = {"colorama", "pywin32", "pywin32_ctypes", "win32_setctime", "pywinpty"}


def pip_python() -> str:
    for rel in (".venv/Scripts/python.exe", ".venv/bin/python"):
        candidate = BACKEND / rel
        if candidate.exists():
            return str(candidate)
    return sys.executable


def pip_command(python: str, target: Path, constraints: Path) -> list[str]:
    platforms = [arg for p in PLATFORMS for arg in ("--platform", p)]
    return [python, "-m", "pip", "install", "-r", str(BACKEND / "requirements.txt"),
            "-c", str(constraints), *platforms, "--implementation", "cp",
            "--python-version", PYTHON_VERSION, "--only-binary=:all:",
            "--no-compile", "--no-cache-dir", "--disable-pip-version-check",
            "--target", str(target)]


def app_files(backend: Path) -> list[Path]:
    """zip に入れるアプリのファイル（backend からの相対パス）。"""
    files = [Path("main.py")]
    files += sorted(p.relative_to(backend) for p in (backend / "app").rglob("*.py")
                    if not EXCLUDED_DIRS.intersection(p.relative_to(backend).parts))
    return files


def wheel_tags(stage: Path) -> dict[str, list[str]]:
    """インストールされた各パッケージの *.dist-info/WHEEL の Tag。"""
    tags: dict[str, list[str]] = {}
    for wheel in sorted(stage.glob("*.dist-info/WHEEL")):
        name = wheel.parent.name.removesuffix(".dist-info")
        lines = wheel.read_text(encoding="utf-8").splitlines()
        tags[name] = [line.split(":", 1)[1].strip() for line in lines if line.startswith("Tag:")]
    return tags


def native_files(stage: Path) -> list[str]:
    return sorted(str(p.relative_to(stage)).replace("\\", "/") for p in stage.rglob("*")
                  if p.is_file() and (p.suffix == ".so" or ".so." in p.name
                                      or p.suffix in FOREIGN_BINARY_SUFFIXES))


def owner_of(path: str, stage: Path) -> str | None:
    """ネイティブ拡張のファイルを含むパッケージ（dist-info の RECORD で判定する）。"""
    for record in stage.glob("*.dist-info/RECORD"):
        entries = {line.split(",", 1)[0] for line in
                   record.read_text(encoding="utf-8").splitlines()}
        if path in entries:
            return record.parent.name.removesuffix(".dist-info")
    return None


def _py_ok(py: str, abi: str) -> bool:
    """cp312 か、abi3 なら cp3NN（NN ≦ 12。安定 ABI は新しい版の Python でも動く）。"""
    if abi == "cp312":
        return py == "cp312"
    if abi == "abi3":
        return all(p.startswith("cp3") and p[3:].isdigit() and int(p[3:]) <= 12
                   for p in py.split("."))
    return False


def tag_ok(tag: str) -> bool:
    py, abi, plat = (tag.split("-") + ["", "", ""])[:3]
    return (_py_ok(py, abi)
            and all(p.startswith("manylinux") and p.endswith("_x86_64")
                    for p in plat.split(".")))


ELF_MAGIC = bytes([0x7F]) + b"ELF"
EM_X86_64 = 62
GLIBC_RE = re.compile(rb"GLIBC_(\d+)\.(\d+)")


def elf_x86_64(data: bytes) -> bool:
    """64 ビット・リトルエンディアン・x86_64 の ELF か（ヘッダーの先頭 20 バイトで判定）。"""
    return (len(data) >= 20 and data[:4] == ELF_MAGIC and data[4] == 2 and data[5] == 1
            and int.from_bytes(data[18:20], "little") == EM_X86_64)


def max_glibc(data: bytes) -> str | None:
    """.so が要求する glibc のシンボルの版の最大値（例 "2.17"）。RUNTIME_GLIBC と比べる。"""
    versions = {(int(a), int(b)) for a, b in GLIBC_RE.findall(data)}
    return "{}.{}".format(*max(versions)) if versions else None


def problems(stage: Path, tags: dict[str, list[str]], natives: list[str]) -> list[str]:
    found = []
    for name in tags:
        dist = name.rsplit("-", 1)[0].lower().replace("-", "_")
        if dist in WINDOWS_ONLY_DISTS:
            found.append(f"Windows 専用の依存が入っています: {name}")
    for record in stage.glob("*.dist-info/RECORD"):
        if any(line.split(",", 1)[0].removeprefix("../../").startswith("bin/")
               for line in record.read_text(encoding="utf-8").splitlines()):
            found.append(f"RECORD が取り除いた bin/ を指しています: {record.parent.name}")
    for f in natives:
        if f.endswith(FOREIGN_BINARY_SUFFIXES):
            found.append(f"Linux 以外のバイナリが入っています: {f}")
            continue
        data = (stage / f).read_bytes()
        if not elf_x86_64(data[:20]):
            found.append(f"x86_64 の ELF ではありません: {f}")
        glibc = max_glibc(data)
        if glibc and tuple(int(x) for x in glibc.split(".")) > RUNTIME_GLIBC:
            found.append(f"glibc {glibc} を要求しています（ランタイムは "
                         f"{'.'.join(map(str, RUNTIME_GLIBC))}）: {f}")
        owner = owner_of(f, stage)
        if owner is None:
            found.append(f"所属するパッケージが分からないネイティブ拡張: {f}")
        elif not tags.get(owner) or not all(tag_ok(t) for t in tags[owner]):
            found.append(f"{owner} の wheel のタグが cp312 / manylinux / x86_64 ではありません: "
                         f"{tags.get(owner)}")
    return found


def drop_from_records(stage: Path, removed: set[str]) -> None:
    """取り除いたファイルの行を dist-info/RECORD からも消す。

    記録と中身を一致させ、zip を再現可能にする。
    """
    if not removed:
        return
    for record in stage.glob("*.dist-info/RECORD"):
        lines = record.read_text(encoding="utf-8").splitlines(keepends=True)
        # RECORD のパスは site-packages からの相対パス。--target では bin/ が "../../bin/..." になる
        kept = [line for line in lines
                if line.split(",", 1)[0].removeprefix("../../") not in removed]
        if len(kept) != len(lines):
            record.write_text("".join(kept), encoding="utf-8", newline="")


def write_zip(stage: Path, zip_path: Path) -> None:
    # 順序は POSIX 形式のパスの文字列で決める（Path の比較は OS で大文字・小文字の扱いが違う）
    files = sorted((p for p in stage.rglob("*") if p.is_file()
                    and "__pycache__" not in p.relative_to(stage).parts),
                   key=lambda p: p.relative_to(stage).as_posix())
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for p in files:
            info = zipfile.ZipInfo(p.relative_to(stage).as_posix(), FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            # どの OS で作っても同じ zip にし、Unix の権限として解釈させる（作成元 = Unix）
            info.create_system = 3
            # 通常のファイル（0o100000）で、全員に読み取りを許可する（Lambda が読めるように）
            info.external_attr = 0o100644 << 16
            zf.writestr(info, p.read_bytes())


def lambda_sha256(path: Path) -> str:
    """Lambda の CodeSha256 と同じ形式（SHA-256 の base64）。アップロード後の照合に使う。"""
    return base64.b64encode(hashlib.sha256(path.read_bytes()).digest()).decode("ascii")


def freeze_constraints(python: str, path: Path) -> bool:
    """テストを実行した環境の版を、そのまま制約にする（-e やローカルのパスは除く）。"""
    res = subprocess.run([python, "-m", "pip", "freeze", "--disable-pip-version-check"],
                         capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        return False
    pins = [line for line in res.stdout.splitlines() if "==" in line and " @ " not in line]
    path.write_text("".join(f"{pin}\n" for pin in pins), encoding="utf-8")
    return True


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    ZIP_PATH.unlink(missing_ok=True)

    python = pip_python()
    if not freeze_constraints(python, CONSTRAINTS_PATH):
        print("pip freeze に失敗しました")
        return 1
    cmd = pip_command(python, STAGE, CONSTRAINTS_PATH)
    print("=== pip:", " ".join(cmd), flush=True)
    if subprocess.run(cmd, env={**os.environ, "PYTHONIOENCODING": "utf-8"}).returncode != 0:
        print("依存のインストールに失敗しました"
              "（対応する Linux 用の wheel がない可能性があります）")
        return 1

    # pip が Windows 上で作る、コマンドの起動用ファイル（bin/*.exe）。Lambda では使わないので除く
    removed = sorted(str(p.relative_to(STAGE)).replace("\\", "/")
                     for p in (STAGE / "bin").rglob("*") if p.is_file())
    shutil.rmtree(STAGE / "bin", ignore_errors=True)
    drop_from_records(STAGE, set(removed))

    for rel in app_files(BACKEND):
        dest = STAGE / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BACKEND / rel, dest)

    tags, natives = wheel_tags(STAGE), native_files(STAGE)
    found = problems(STAGE, tags, natives)
    unzipped = sum(p.stat().st_size for p in STAGE.rglob("*") if p.is_file())
    if unzipped > UNZIPPED_LIMIT:
        found.append(f"展開後のサイズが上限を超えています: {unzipped} bytes")
    if not found:
        write_zip(STAGE, ZIP_PATH)
        if ZIP_PATH.stat().st_size > ZIP_LIMIT:
            found.append(f"zip のサイズが上限を超えています: {ZIP_PATH.stat().st_size} bytes")

    report = {
        "platforms": list(PLATFORMS), "python_version": PYTHON_VERSION,
        "app_files": [str(p).replace("\\", "/") for p in app_files(BACKEND)],
        "removed_console_scripts": removed, "wheel_tags": tags, "native_files": natives,
        "native_max_glibc": {f: max_glibc((STAGE / f).read_bytes()) for f in natives},
        "unzipped_bytes": unzipped,
        "zip_bytes": ZIP_PATH.stat().st_size if ZIP_PATH.exists() else None,
        "zip_code_sha256": lambda_sha256(ZIP_PATH) if ZIP_PATH.exists() else None,
        "problems": found,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if found:
        ZIP_PATH.unlink(missing_ok=True)
        print("\n=== build_lambda: FAILED（zip は作っていません）")
        return 1
    print(f"\n=== build_lambda: OK → {ZIP_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
