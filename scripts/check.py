#!/usr/bin/env python
"""プロジェクト共通の品質ゲート。

人手・Claude Code の Stop Hook・CI のすべてがこのスクリプトを入口にする。
標準ライブラリのみで書き、Python 3.10 以上で動く（起動用の python は何でもよい）。
実際の lint / test は backend/.venv の Python 3.12 で実行する。

終了コード:
    0  全チェック成功
    1  いずれかのチェックが失敗
    2  実行環境の不備（venv が無い等）でチェックできなかった
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

EXIT_OK, EXIT_FAILED, EXIT_ENV = 0, 1, 2


def backend_python() -> Path | None:
    """backend の venv の Python を返す。CI 等で venv を使わない場合は CHECK_PYTHON で上書き可。"""
    override = os.environ.get("CHECK_PYTHON")
    if override:
        resolved = shutil.which(override)
        return Path(resolved) if resolved else None
    for rel in (".venv/Scripts/python.exe", ".venv/bin/python"):
        candidate = BACKEND / rel
        if candidate.exists():
            return candidate
    return None


def run(name: str, cmd: list[str], cwd: Path) -> bool:
    print(f"\n=== {name}: {' '.join(cmd)}", flush=True)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(cmd, cwd=cwd, env=env)
    ok = result.returncode == 0
    print(f"--- {name}: {'OK' if ok else f'FAILED (exit {result.returncode})'}", flush=True)
    return ok


def check_backend() -> int:
    py = backend_python()
    if py is None:
        print("backend の Python が見つかりません（backend/.venv または CHECK_PYTHON）。"
              "CLAUDE.md のセットアップ手順で venv を作成してください。")
        return EXIT_ENV
    results = [
        run("ruff", [str(py), "-m", "ruff", "check", "backend", "scripts"], ROOT),
        run("pytest", [str(py), "-m", "pytest"], BACKEND),
    ]
    return EXIT_OK if all(results) else EXIT_FAILED


def check_frontend() -> int:
    """frontend/ が存在する場合のみ、package.json に定義済みの検証スクリプトを実行する。"""
    package_json = FRONTEND / "package.json"
    if not package_json.exists():
        return EXIT_OK
    if not (FRONTEND / "node_modules").exists():
        print("frontend/node_modules が見つかりません。`npm ci` を実行してください。")
        return EXIT_ENV
    npm = shutil.which("npm")
    if npm is None:
        print("npm が見つかりません。")
        return EXIT_ENV
    scripts = json.loads(package_json.read_text(encoding="utf-8")).get("scripts", {})
    results = [
        run(f"npm {name}", [npm, "run", name], FRONTEND)
        for name in ("lint", "typecheck", "test")
        if name in scripts
    ]
    return EXIT_OK if all(results) else EXIT_FAILED


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", nargs="?", choices=("all", "backend", "frontend"), default="all")
    args = parser.parse_args()

    codes = []
    if args.target in ("all", "backend"):
        codes.append(check_backend())
    if args.target in ("all", "frontend"):
        codes.append(check_frontend())

    code = max(codes)
    summary = {EXIT_OK: "ALL PASSED", EXIT_FAILED: "FAILED", EXIT_ENV: "ENVIRONMENT ERROR"}[code]
    print(f"\n=== check.py: {summary}")
    return code


if __name__ == "__main__":
    sys.exit(main())
