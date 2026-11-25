"""Nominatim の実 API を使った最小限のスモークテスト（手動実行用。pytest には含めない）。

使い方（リポジトリのルートで実行）:
    EXTERNAL_APIS_ENABLED=true backend/.venv/Scripts/python.exe backend/tools/smoke_nominatim.py

外部 API への送信は既定で無効（plan §7.3）。実行するときだけ、上のように明示的に有効にする。

利用条件（docs/engineering-notes.md §9.3・§9.5）を守るため：
- 検索するのは、公開施設・駅名の 2 語だけ（2 リクエスト）。ループや自動の再実行はしない。
- アプリのリミッター（1.1 秒以上の間隔・直列・初回も待つ・リトライなし）と
  User-Agent をそのまま使う。
- 開発サーバーと同時に実行しない。
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.places import PlacesClient  # noqa: E402

QUERIES = ("大阪城公園", "なんば駅")


def main() -> int:
    client = PlacesClient()
    for q in QUERIES:
        t = time.monotonic()
        places = client.search(q)  # 初回の待機 1.1 秒（2 回目は前回から 1.1 秒）を含む
        total = time.monotonic() - t
        print(f"「{q}」：{len(places)} 件（待機を含めて {total:.2f} 秒）")
        for p in places:
            print(f"  - {p.name} / {p.label} ({p.lat:.5f}, {p.lon:.5f})")
    print(f"送信 {client.limiter.sent} 回")
    return 0


if __name__ == "__main__":
    sys.exit(main())
