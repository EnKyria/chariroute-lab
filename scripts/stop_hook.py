#!/usr/bin/env python
"""Claude Code の Stop Hook。応答終了時に品質ゲート (scripts/check.py) を検証する。

設計:
- 対象ファイルに変更が無ければ何もしない（会話だけのターンで毎回テストを走らせない）。
- 失敗時は 1 回だけ decision=block で Claude に差し戻す。
- 差し戻し後の再停止 (stop_hook_active=true) では二度と block せず、
  失敗が残っていれば systemMessage でユーザーに知らせて終了させる（無限ループ防止）。
- 環境不備・タイムアウトはコードの問題ではないので block しない。

標準ライブラリのみ。Python 3.10 以上で動作する。
stdout には Claude Code が解釈する JSON だけを出力する。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / ".claude" / ".cache" / "stop-hook-state.json"
CHECK_SCRIPT = ROOT / "scripts" / "check.py"
TIMEOUT_SEC = 240
MAX_REASON_CHARS = 4000

WATCH_DIRS = ("backend", "frontend", "scripts")
WATCH_FILES = ("pyproject.toml",)  # ルートの ruff 設定
WATCH_SUFFIXES = {".py", ".toml", ".txt", ".ts", ".tsx", ".js", ".jsx", ".json", ".css", ".html"}
SKIP_DIRS = {"node_modules", "dist", "build", "__pycache__", ".pytest_cache", ".ruff_cache"}


def fingerprint() -> str:
    """監視対象ファイルのパス・サイズ・更新時刻からハッシュを作る。"""
    h = hashlib.sha256()
    for top in WATCH_DIRS:
        base = ROOT / top
        if not base.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(
                d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".venv")
            )
            for name in sorted(filenames):
                path = Path(dirpath) / name
                if path.suffix not in WATCH_SUFFIXES:
                    continue
                st = path.stat()
                h.update(f"{path.relative_to(ROOT)}|{st.st_size}|{st.st_mtime_ns}\n".encode())
    return h.hexdigest()


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(fp: str, code: int) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"fingerprint": fp, "exit_code": code}), encoding="utf-8")


def emit(payload: dict) -> None:
    # ensure_ascii=True: Windows のコンソール文字コードに依存せず JSON を渡す
    print(json.dumps(payload, ensure_ascii=True))


def main() -> int:
    try:
        hook_input = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        hook_input = {}
    already_continued = bool(hook_input.get("stop_hook_active"))

    fp = fingerprint()
    state = load_state()

    if state.get("fingerprint") == fp:
        # 前回チェック以降、変更なし → 再実行しない
        if state.get("exit_code") == 1 and already_continued:
            emit({"systemMessage": "[stop-hook] 品質チェックは失敗したままです。"
                                   "`python scripts/check.py` で確認してください。"})
        return 0

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        proc = subprocess.run(
            [sys.executable, str(CHECK_SCRIPT)],
            cwd=ROOT, env=env, capture_output=True, timeout=TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        emit({"systemMessage": f"[stop-hook] 品質チェックが {TIMEOUT_SEC} 秒でタイムアウトしました"
                               "（ブロックせず終了します）。"})
        return 0

    code = proc.returncode
    output = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
    if code in (0, 1):
        # 環境不備 (2) は保存しない。venv を直した後、ファイル変更がなくても再チェックさせるため
        save_state(fp, code)

    if code == 0:
        return 0

    if code != 1:
        emit({"systemMessage": "[stop-hook] 実行環境の不備で品質チェックを実行できませんでした"
                               f"（ブロックせず終了します）。\n{output[-1000:]}"})
        return 0

    if already_continued:
        emit({"systemMessage": "[stop-hook] 修正後も品質チェックが失敗しています。"
                               "未解決のまま終了します。"})
        return 0

    emit({
        "decision": "block",
        "reason": (
            "scripts/check.py の品質チェックが失敗しました。原因を調べて修正してください。"
            "テストを削除・skip して通すことは禁止です。"
            "修正できない場合は理由をユーザーに報告して終了してください。\n\n"
            + output[-MAX_REASON_CHARS:]
        ),
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
