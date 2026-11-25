"""FOSSGIS OSRM の実 API を使った最小限のスモークテスト（手動実行用。pytest には含めない）。

使い方（リポジトリのルートで実行）:
    backend/.venv/Scripts/python.exe backend/tools/smoke_osrm.py

利用条件（docs/engineering-notes.md §9.5）を守るため：
- 送るのは 1 回の経路検索の分だけ（Table 2 回 + Route 3 回 = 5 回）。
  ループや再実行の自動化はしない。
- アプリのリミッター（1.1 秒以上の間隔・直列・初回も待つ・リトライなし）と
  User-Agent をそのまま使う。
- 開発サーバー（uvicorn）を止めてから実行する（FOSSGIS への同時接続を 1 つに保つため）。
- 地点は公開のプリセット（梅田 → 難波）だけを使う。

確認すること（plan §6.5 の確定の条件）：
- Table に annotations=distance を付けて、徒歩・自転車とも distances（道路距離）が返ること
- 応答の形式（code、sources/destinations の distance、Route の GeoJSON）が実装の想定と一致すること
- Table と Route の距離の差、直線距離モデルとの差
"""

import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.gbfs import GbfsClient  # noqa: E402
from app.osrm import OsrmClient  # noqa: E402
from app.outbound import HttpResult, http_get_json  # noqa: E402
from app.presets import find_preset  # noqa: E402
from app.road_routing import search_road_route  # noqa: E402
from app.routing import Point, search_route  # noqa: E402

MAX_REQUESTS = 5
# 計測用：リクエストごとのタイムアウトだけを引数で長くできる（既定はアプリと同じ）
TIMEOUT = float(sys.argv[1]) if len(sys.argv) > 1 else None


def print_log(log: list[dict[str, Any]]) -> None:
    for i, e in enumerate(log):
        gap = "" if i == 0 else f"（前回の送信から {e['at'] - log[i - 1]['at']:.2f} 秒）"
        print(f"  {i + 1}. {e['service']}/{e['profile']} HTTP {e['status']} code={e['code']} "
              f"{e['elapsed']:.2f} 秒{gap}")
        if e["service"] == "table":
            print(f"     distances あり={e['has_distances']} 要素 {e['cells']} 件、"
                  f"null {e['nulls']} 件、スナップ距離（出発地/目的地側）{e['snaps']} m")
        else:
            print(f"     distance={e['route_distance']} m duration={e['route_duration']} 秒 "
                  f"geometry={e['geometry_type']}")
    print(f"  User-Agent: {log[0]['ua'] if log else '-'}")


def main() -> int:
    log: list[dict[str, Any]] = []

    def recording_fetch(url: str, timeout: float, headers: dict[str, str]) -> HttpResult:
        if len(log) >= MAX_REQUESTS:
            raise RuntimeError("送信の上限（5 回）を超えようとしました")
        service = "table" if "/table/" in url else "route"
        profile = "foot" if "routed-foot" in url else "bike"
        t = time.monotonic()
        res = http_get_json(url, timeout, headers)
        body = res.body if isinstance(res.body, dict) else {}
        log.append({
            "at": t, "service": service, "profile": profile, "status": res.status,
            "code": body.get("code"), "elapsed": time.monotonic() - t,
            "has_distances": "distances" in body,
            "nulls": sum(v is None for row in body.get("distances") or [] for v in row),
            "cells": sum(len(row) for row in body.get("distances") or []),
            "snaps": [round(w.get("distance", -1), 1) for w in body.get("sources", [])[:1]]
                     + [round(w.get("distance", -1), 1) for w in body.get("destinations", [])[-1:]],
            "route_distance": (body.get("routes") or [{}])[0].get("distance"),
            "route_duration": (body.get("routes") or [{}])[0].get("duration"),
            "geometry_type": ((body.get("routes") or [{}])[0].get("geometry") or {}).get("type"),
            "ua": headers.get("User-Agent"),
        })
        return res

    o, d = find_preset("umeda"), find_preset("namba")
    assert o and d
    origin, dest = Point(o.lat, o.lon), Point(d.lat, d.lon)
    snapshot = GbfsClient().get_snapshot()
    print(f"GBFS：大阪エリアのポート {len(snapshot.stations)} 件")

    osrm = (OsrmClient(fetch=recording_fetch) if TIMEOUT is None
            else OsrmClient(fetch=recording_fetch, timeout=TIMEOUT, table_timeout=TIMEOUT))
    print(f"タイムアウト：Table {osrm.table_timeout} 秒、Route {osrm.timeout} 秒")
    started = time.monotonic()
    try:
        result = search_road_route(origin, dest, snapshot.stations, osrm,
                                   deadline=osrm.clock() + 60)
    finally:
        print(f"OSRM：送信 {osrm.limiter.sent} 回、合計 {time.monotonic() - started:.1f} 秒")
        print_log(log)

    r = result.route
    if r is None:
        print("経路なし（bike_share: null）")
        return 1
    print(f"候補：貸出 {result.rent_candidates} 件、返却 {result.return_candidates} 件、"
          f"評価した組 {result.pairs_evaluated}")
    print(f"選んだ組：{r.rent_station.name} → {r.return_station.name}")
    for leg in r.legs:
        print(f"  {leg.mode:<4} 道路距離 {leg.distance_m:7.1f} m  推定 {leg.minutes:5.1f} 分  "
              f"形状の点 {len(leg.geometry)}")
    print(f"合計（Route の距離）{r.total_minutes:.1f} 分 / 選択に使った Table の値 "
          f"{r.table_total_minutes:.1f} 分")
    linear = search_route(origin, dest, snapshot.stations).bike
    if linear:
        print(f"直線距離モデル（比較）：{linear.rent_station.name} → {linear.return_station.name} "
              f"{linear.total_minutes:.1f} 分")
    return 0


if __name__ == "__main__":
    sys.exit(main())
