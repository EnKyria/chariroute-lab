"""道路モデルの経路探索（plan §6.4・6.5）。

1. 直線距離で候補を絞る：貸出は出発地から近い順に 10 件、返却は目的地から近い順に 10 件。
   さらに直線距離モデル（app/routing.py の分枝限定法）の最適な組を加える
   （重複は除く。最大 11 件ずつ）。
2. OSRM の Table を 2 回（徒歩・自転車）呼び、候補の全ての組（最大 121 組）を
   道路距離で評価する。
3. 最小の組について Route を 3 回呼び、経路の形状と距離を取得する。
   表示の距離・分は Route の距離で計算する。

所要時間 = 道路距離 ÷ ChariRoute の速度 + 貸出・返却の手続き時間（推定値）。
OSRM の duration は使わない。
最適解は「候補の中で」だけ保証する（全てのポートの組での最適解は保証しない）。

ログには座標を出さない（候補数・評価した組の数・Table と Route の差の割合だけ）。
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.osrm import OsrmClient, OsrmNoRoute
from app.routing import Point, Station, can_rent, can_return, haversine_m, search_route

logger = logging.getLogger("chariroute.road")


@dataclass(frozen=True)
class RoadParams:
    walk_kmh: float = 4.8
    bike_kmh: float = 15.0
    rent_minutes: float = 1.0
    return_minutes: float = 1.0
    nearest_candidates: int = 10
    max_snap_m: float = 300.0  # 出発地・目的地から道路までの距離の上限
    mismatch_ratio: float = 0.10  # Table と Route の差の警告のしきい値（割合かつ距離）
    mismatch_m: float = 100.0

    def minutes(self, distance_m: float, mode: Literal["walk", "bike"]) -> float:
        kmh = self.walk_kmh if mode == "walk" else self.bike_kmh
        return distance_m / (kmh * 1000 / 60)


DEFAULT_ROAD_PARAMS = RoadParams()


class NoNearbyRoad(Exception):
    """出発地か目的地の近くに道路がない（400 にする）。"""

    def __init__(self, which: Literal["origin", "destination"]) -> None:
        super().__init__(which)
        self.which = which


@dataclass(frozen=True)
class Leg:
    mode: Literal["walk", "bike"]
    distance_m: float
    minutes: float
    geometry: list[tuple[float, float]]


@dataclass(frozen=True)
class RoadRoute:
    rent_station: Station
    return_station: Station
    legs: tuple[Leg, Leg, Leg]
    rent_minutes: float
    return_minutes: float
    total_minutes: float
    table_total_minutes: float  # 組の選択に使った Table の値での合計（評価用）


@dataclass(frozen=True)
class RoadSearchResult:
    route: RoadRoute | None  # 利用できる組がなければ None
    rent_candidates: int
    return_candidates: int
    pairs_evaluated: int


def _pt(s: Station) -> Point:
    return Point(s.lat, s.lon)


def select_candidates(origin: Point, destination: Point, stations: Sequence[Station],
                      params: RoadParams = DEFAULT_ROAD_PARAMS
                      ) -> tuple[list[Station], list[Station]]:
    """直線距離で候補を絞る。順序は決定的（距離、ID の順）。"""
    rentable = sorted((s for s in stations if can_rent(s)),
                      key=lambda s: (haversine_m(origin, _pt(s)), s.station_id))
    returnable = sorted((s for s in stations if can_return(s)),
                        key=lambda s: (haversine_m(_pt(s), destination), s.station_id))
    rent = rentable[:params.nearest_candidates]
    ret = returnable[:params.nearest_candidates]
    best = search_route(origin, destination, stations).bike
    if best is not None:
        if all(s.station_id != best.rent_station.station_id for s in rent):
            rent.append(best.rent_station)
        if all(s.station_id != best.return_station.station_id for s in ret):
            ret.append(best.return_station)
    return rent, ret


def _check_mismatch(mode: str, table_m: float, route_m: float, params: RoadParams) -> None:
    diff = abs(route_m - table_m)
    base = max(table_m, 1.0)
    if diff > params.mismatch_m and diff / base > params.mismatch_ratio:
        logger.warning("Table と Route の距離の差が大きい: mode=%s diff_ratio=%.2f",
                       mode, diff / base)


def search_road_route(origin: Point, destination: Point, stations: Sequence[Station],
                      osrm: OsrmClient, deadline: float | None = None,
                      params: RoadParams = DEFAULT_ROAD_PARAMS) -> RoadSearchResult:
    """道路距離で最小の組を探す。OSRM の失敗は OsrmError のまま呼び出し側へ送る。"""
    rent, ret = select_candidates(origin, destination, stations, params)
    if not rent or not ret:
        return RoadSearchResult(None, len(rent), len(ret), 0)
    nr, nt = len(rent), len(ret)

    try:
        # 徒歩：地点 [O, 貸出…, 返却…, D]、sources=[O, 返却…]、destinations=[貸出…, D]
        foot_points = [origin, *map(_pt, rent), *map(_pt, ret), destination]
        foot = osrm.table("foot", foot_points,
                          sources=[0, *range(1 + nr, 1 + nr + nt)],
                          destinations=[*range(1, 1 + nr), 1 + nr + nt], deadline=deadline)
        if foot.source_snap_m[0] > params.max_snap_m:
            raise NoNearbyRoad("origin")
        if foot.destination_snap_m[-1] > params.max_snap_m:
            raise NoNearbyRoad("destination")
        walk_to_rent = foot.distances[0][:nr]  # O → 貸出候補
        walk_from_return = [foot.distances[1 + j][nr] for j in range(nt)]  # 返却候補 → D

        # 自転車：地点 [貸出…, 返却…]、貸出 × 返却
        bike = osrm.table("bike", [*map(_pt, rent), *map(_pt, ret)],
                          sources=list(range(nr)), destinations=list(range(nr, nr + nt)),
                          deadline=deadline)
    except OsrmNoRoute:
        return RoadSearchResult(None, nr, nt, 0)

    best: tuple[float, str, str, int, int] | None = None
    pairs = 0
    for i, a in enumerate(rent):
        d_oa = walk_to_rent[i]
        if d_oa is None:
            continue  # 徒歩で到達できない貸出ポート
        for j, b in enumerate(ret):
            d_bd, d_ab = walk_from_return[j], bike.distances[i][j]
            if a.station_id == b.station_id or d_bd is None or d_ab is None:
                continue
            pairs += 1
            total = (params.minutes(d_oa, "walk") + params.rent_minutes
                     + params.minutes(d_ab, "bike") + params.return_minutes
                     + params.minutes(d_bd, "walk"))
            key = (total, a.station_id, b.station_id, i, j)
            if best is None or key[:3] < best[:3]:
                best = key
    if best is None:
        return RoadSearchResult(None, nr, nt, pairs)

    table_total, _, _, i, j = best
    a, b = rent[i], ret[j]
    table_m = (walk_to_rent[i], bike.distances[i][j], walk_from_return[j])
    try:
        shapes = (osrm.route("foot", origin, _pt(a), deadline),
                  osrm.route("bike", _pt(a), _pt(b), deadline),
                  osrm.route("foot", _pt(b), destination, deadline))
    except OsrmNoRoute:
        return RoadSearchResult(None, nr, nt, pairs)

    modes: tuple[Literal["walk", "bike"], ...] = ("walk", "bike", "walk")
    legs = []
    for mode, shape, t_m in zip(modes, shapes, table_m, strict=True):
        if t_m is not None:
            _check_mismatch(mode, t_m, shape.distance_m, params)
        legs.append(Leg(mode, shape.distance_m, params.minutes(shape.distance_m, mode),
                        shape.geometry))
    total = sum(leg.minutes for leg in legs) + params.rent_minutes + params.return_minutes
    route = RoadRoute(a, b, (legs[0], legs[1], legs[2]), params.rent_minutes,
                      params.return_minutes, total, table_total)
    return RoadSearchResult(route, nr, nt, pairs)
