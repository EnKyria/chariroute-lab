"""scripts/build_lambda.py の判定部分のテスト（pip・ネットワークは使わない）。plan §7.4。"""

import importlib.util
import zipfile
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build_lambda.py"
_spec = importlib.util.spec_from_file_location("build_lambda", _SCRIPT)
assert _spec is not None and _spec.loader is not None
bl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bl)

BACKEND = Path(__file__).resolve().parents[1]
ELF_X86_64 = b"\x7fELF\x02\x01\x01" + b"\x00" * 11 + (62).to_bytes(2, "little")
ELF_AARCH64 = b"\x7fELF\x02\x01\x01" + b"\x00" * 11 + (183).to_bytes(2, "little")


def test_app_files_are_main_and_app_only():
    files = [str(p).replace("\\", "/") for p in bl.app_files(BACKEND)]
    assert files[0] == "main.py"
    assert "app/security.py" in files and "app/outbound.py" in files
    assert all(f == "main.py" or f.startswith("app/") for f in files)
    assert not any("tests" in f or "tools" in f or "__pycache__" in f for f in files)


def test_pip_command_targets_linux_cp312_binary_only(tmp_path):
    cmd = bl.pip_command("python", tmp_path / "t", tmp_path / "c.txt")
    joined = " ".join(cmd)
    assert "--only-binary=:all:" in cmd
    assert "--implementation cp" in joined and "--python-version 3.12" in joined
    for plat in ("manylinux_2_28_x86_64", "manylinux_2_17_x86_64", "manylinux2014_x86_64"):
        assert f"--platform {plat}" in joined
    assert f"-c {tmp_path / 'c.txt'}" in joined  # テストした版に固定する


@pytest.mark.parametrize("tag,ok", [
    ("cp312-cp312-manylinux_2_17_x86_64", True),
    ("cp312-cp312-manylinux_2_28_x86_64", True),
    ("cp312-abi3-manylinux2014_x86_64", True),
    ("cp39-abi3-manylinux_2_17_x86_64", True),  # 安定 ABI は新しい Python でも動く
    ("cp313-abi3-manylinux_2_17_x86_64", False),
    ("cp39-cp39-manylinux_2_17_x86_64", False),
    ("cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64", True),
    ("cp312-cp312-win_amd64", False),
    ("cp312-cp312-manylinux_2_17_aarch64", False),
    ("cp311-cp311-manylinux_2_17_x86_64", False),
    ("cp312-cp312-musllinux_1_2_x86_64", False),
    ("cp312-cp312-macosx_11_0_x86_64", False),
    ("py3-none-any", False),
])
def test_tag_ok(tag, ok):
    assert bl.tag_ok(tag) is ok


def test_elf_and_glibc_detection():
    assert bl.elf_x86_64(ELF_X86_64)
    assert not bl.elf_x86_64(ELF_AARCH64)
    assert not bl.elf_x86_64(b"MZ\x90\x00" + b"\x00" * 16)  # Windows の PE
    assert bl.max_glibc(b"..GLIBC_2.2.5..GLIBC_2.14..GLIBC_2.3.4..") == "2.14"
    assert bl.max_glibc(b"no symbols") is None


def _stage(tmp_path: Path, tag: str, so: bytes = ELF_X86_64, extra: str | None = None) -> Path:
    stage = tmp_path / "stage"
    (stage / "pkg").mkdir(parents=True)
    (stage / "pkg" / "_ext.cpython-312-x86_64-linux-gnu.so").write_bytes(so)
    di = stage / "pkg-1.0.dist-info"
    di.mkdir()
    (di / "WHEEL").write_text(f"Wheel-Version: 1.0\nTag: {tag}\n", encoding="utf-8")
    record = "pkg/_ext.cpython-312-x86_64-linux-gnu.so,sha256=x,1\n"
    if extra:
        (stage / extra).parent.mkdir(parents=True, exist_ok=True)
        (stage / extra).write_bytes(b"MZ")
        record += f"{extra},sha256=y,1\n"
    (di / "RECORD").write_text(record, encoding="utf-8")
    return stage


def _problems(stage: Path) -> list[str]:
    return bl.problems(stage, bl.wheel_tags(stage), bl.native_files(stage))


def test_problems_none_for_linux_x86_64_wheel(tmp_path):
    assert _problems(_stage(tmp_path, "cp312-cp312-manylinux_2_17_x86_64")) == []


def test_problems_for_windows_wheel_tag(tmp_path):
    found = _problems(_stage(tmp_path, "cp312-cp312-win_amd64"))
    assert len(found) == 1 and "pkg-1.0" in found[0]


def test_problems_for_non_x86_64_binary(tmp_path):
    found = _problems(_stage(tmp_path, "cp312-cp312-manylinux_2_17_x86_64", ELF_AARCH64))
    assert any("ELF" in f for f in found)


def test_problems_for_windows_binaries(tmp_path):
    found = _problems(_stage(tmp_path, "cp312-cp312-manylinux_2_17_x86_64",
                             extra="pkg/_ext.pyd"))
    assert any("Linux 以外" in f for f in found)


def test_problems_for_glibc_newer_than_runtime(tmp_path):
    ok = _stage(tmp_path / "a", "cp312-cp312-manylinux_2_28_x86_64",
                ELF_X86_64 + b"GLIBC_2.34\x00GLIBC_2.17")
    assert _problems(ok) == []
    ng = _stage(tmp_path / "b", "cp312-cp312-manylinux_2_39_x86_64",
                ELF_X86_64 + b"GLIBC_2.35\x00GLIBC_2.17")
    assert any("glibc 2.35" in f for f in _problems(ng))


def test_problems_for_windows_only_dist(tmp_path):
    stage = _stage(tmp_path, "cp312-cp312-manylinux_2_17_x86_64")
    di = stage / "colorama-0.4.6.dist-info"
    di.mkdir()
    (di / "WHEEL").write_text("Tag: py2.py3-none-any\n", encoding="utf-8")
    assert any("colorama" in f for f in _problems(stage))


def test_problems_when_record_still_points_to_bin(tmp_path):
    stage = _stage(tmp_path, "cp312-cp312-manylinux_2_17_x86_64")
    record = stage / "pkg-1.0.dist-info" / "RECORD"
    record.write_text(record.read_text(encoding="utf-8") + "../../bin/pkg.exe,sha256=z,1\n",
                      encoding="utf-8")
    assert any("bin/" in f for f in _problems(stage))


def test_drop_from_records_handles_relative_bin_paths(tmp_path):
    di = tmp_path / "x-1.0.dist-info"
    di.mkdir()
    (di / "RECORD").write_text("../../bin/x.exe,sha256=a,1\nx/__init__.py,sha256=b,2\n",
                               encoding="utf-8", newline="")
    bl.drop_from_records(tmp_path, {"bin/x.exe"})
    assert (di / "RECORD").read_text(encoding="utf-8") == "x/__init__.py,sha256=b,2\n"


def test_write_zip_is_reproducible_and_skips_pycache(tmp_path):
    stage = tmp_path / "s"
    (stage / "app" / "__pycache__").mkdir(parents=True)
    (stage / "main.py").write_text("x = 1\n", encoding="utf-8")
    (stage / "app" / "a.py").write_text("y = 2\n", encoding="utf-8")
    (stage / "app" / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"\x00")
    z1, z2 = tmp_path / "1.zip", tmp_path / "2.zip"
    bl.write_zip(stage, z1)
    bl.write_zip(stage, z2)
    assert z1.read_bytes() == z2.read_bytes()
    with zipfile.ZipFile(z1) as zf:
        assert zf.namelist() == ["app/a.py", "main.py"]
        for i in zf.infolist():
            assert i.create_system == 3  # どの OS で作っても Unix として記録する
            assert i.external_attr >> 16 == 0o100644  # 通常のファイル・全員が読める
    assert len(bl.lambda_sha256(z1)) == 44  # SHA-256 の base64
