"""実際の GBFS を使った疎通確認と性能計測（手動実行用。pytest には含めない）。

使い方（リポジトリのルートで実行）:
    backend/.venv/Scripts/python.exe backend/tools/smoke_gbfs.py

確認すること：
- 実フィードを取得・検証でき、大阪エリアのポート数が妥当であること
- 全プリセットの組み合わせで経路を計算でき、利用不可のポートを含まないこと
- 経路計算（分枝限定法）の時間と評価した組の数、素朴な全組の総当たりとの結果と時間の比較
"""

import itertools
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.gbfs import GbfsClient  # noqa: E402
from app.presets import PRESETS  # noqa: E402
from app.routing import (  # noqa: E402
    DEFAULT_PARAMS,
    Point,
    Station,
    can_rent,
    can_return,
    haversine_m,
    search_route,
    travel_minutes,
)


def naive_best(o: Point, d: Point, stations: tuple[Station, ...]) -> tuple[float, str, str]:
    """全ての（貸出, 返却）の組を素朴に総当たりする（比較用）。"""
    p = DEFAULT_PARAMS
    best: tuple[float, str, str] | None = None
    for a in stations:
        if not can_rent(a):
            continue
        pa = Point(a.lat, a.lon)
        t_a = travel_minutes(haversine_m(o, pa), p.walk_kmh, p.detour_factor)
        for b in stations:
            if not can_return(b) or a.station_id == b.station_id:
                continue
            pb = Point(b.lat, b.lon)
            t = (t_a + p.rent_minutes + p.return_minutes
                 + travel_minutes(haversine_m(pa, pb), p.bike_kmh, p.detour_factor)
                 + travel_minutes(haversine_m(pb, d), p.walk_kmh, p.detour_factor))
            key = (t, a.station_id, b.station_id)
            if best is None or key < best:
                best = key
    assert best is not None
    return best


def main() -> int:
    t0 = time.perf_counter()
    snap = GbfsClient().get_snapshot()
    t_fetch = time.perf_counter() - t0
    st = snap.stations
    print(f"取得と検証: {t_fetch:.2f}s / 大阪エリアのポート {len(st)} 件 / "
          f"貸出可能 {sum(map(can_rent, st))} / 返却可能 {sum(map(can_return, st))} / "
          f"捨てたレコード {snap.discarded_records} / last_updated {snap.last_updated}")

    times: list[float] = []
    naive_times: list[float] = []
    pairs: list[int] = []
    mismatches = 0
    for o, d in itertools.permutations(PRESETS, 2):
        po, pd = Point(o.lat, o.lon), Point(d.lat, d.lon)
        t = time.perf_counter()
        r = search_route(po, pd, st)
        times.append(time.perf_counter() - t)
        pairs.append(r.pairs_evaluated)
        t = time.perf_counter()
        naive = naive_best(po, pd, st)
        naive_times.append(time.perf_counter() - t)
        b = r.bike
        assert b is not None and can_rent(b.rent_station) and can_return(b.return_station)
        if (b.rent_station.station_id, b.return_station.station_id) != naive[1:]:
            mismatches += 1
        print(f"{o.id:>14} -> {d.id:<14} 自転車 {b.total_minutes:5.1f} 分 / "
              f"評価した組 {r.pairs_evaluated:>5} / "
              f"{b.rent_station.name} → {b.return_station.name}")
    times.sort()
    naive_times.sort()
    pairs.sort()
    n_all = sum(map(can_rent, st)) * sum(map(can_return, st))
    mid = len(times) // 2
    print(f"分枝限定法: {len(times)} 組、1 回の計算時間 中央値 {times[mid] * 1000:.2f}ms "
          f"最大 {times[-1] * 1000:.2f}ms、評価した組 中央値 {pairs[mid]} 最大 {pairs[-1]}"
          f"（全組 約 {n_all:,}）")
    print(f"素朴な総当たり: 中央値 {naive_times[mid] * 1000:.1f}ms "
          f"最大 {naive_times[-1] * 1000:.1f}ms、結果が異なった組 {mismatches} 件")
    return 0 if mismatches == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
