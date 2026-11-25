"""経路計算（純粋関数）。HTTP や GBFS の取得には依存しない。

PHASE 4.5 以降は「直線距離モデル」として、道路モデル（app/road_routing.py）の候補の絞り込みと、
評価での比較に使う。徒歩のみの経路とおすすめの判定は、仕様の変更（plan §6.3）で削除した。

合計所要時間 = 徒歩(出発地→貸出ポート) + 貸出手続き + 自転車(貸出→返却ポート) + 返却手続き
              + 徒歩(返却ポート→目的地)
各区間の距離は「ハバーサイン式の直線距離 × 迂回係数」で概算する。
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass

EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class RouteParams:
    walk_kmh: float = 4.8
    bike_kmh: float = 15.0
    detour_factor: float = 1.3
    rent_minutes: float = 1.0
    return_minutes: float = 1.0


DEFAULT_PARAMS = RouteParams()


@dataclass(frozen=True)
class Point:
    lat: float
    lon: float


@dataclass(frozen=True)
class Station:
    """station_information と station_status を結合したポート。"""

    station_id: str
    name: str
    lat: float
    lon: float
    capacity: int | None
    is_installed: bool
    is_renting: bool
    is_returning: bool
    num_bikes_available: int
    num_docks_available: int
    last_reported: int | None


@dataclass(frozen=True)
class BikeRoute:
    rent_station: Station
    return_station: Station
    walk_to_rent_m: float
    bike_m: float
    walk_from_return_m: float
    walk_to_rent_minutes: float
    rent_minutes: float
    bike_minutes: float
    return_minutes: float
    walk_from_return_minutes: float
    total_minutes: float


@dataclass(frozen=True)
class SearchResult:
    bike: BikeRoute | None  # 利用可能なポートの組がない場合は None
    rent_candidates: int
    return_candidates: int
    pairs_evaluated: int


def haversine_m(a: Point, b: Point) -> float:
    """2 点間の大円距離（メートル）。"""
    phi1, phi2 = math.radians(a.lat), math.radians(b.lat)
    dphi = phi2 - phi1
    dlmb = math.radians(b.lon - a.lon)
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def travel_minutes(straight_m: float, kmh: float, detour_factor: float) -> float:
    return straight_m * detour_factor / (kmh * 1000 / 60)


def can_rent(s: Station) -> bool:
    return s.is_installed and s.is_renting and s.num_bikes_available > 0


def can_return(s: Station) -> bool:
    return s.is_installed and s.is_returning and s.num_docks_available > 0


def _point(s: Station) -> Point:
    return Point(s.lat, s.lon)


# 浮動小数点の丸め誤差で、下限が実際の値をわずかに上回っても枝を刈らないための余裕（分）
_PRUNE_EPS = 1e-9


def search_route(origin: Point, destination: Point, stations: Iterable[Station],
                 params: RouteParams = DEFAULT_PARAMS) -> SearchResult:
    """利用可能な全ての（貸出ポート, 返却ポート）の組から、合計所要時間が最小の組を返す。

    結果は全組の総当たりと同じ（この所要時間モデルでの最適解を保証する）。
    計算を減らすため、最適解になりえない組を下限で打ち切る（分枝限定法）。

    下限の根拠（O：出発地、A：貸出、B：返却、D：目的地、d：直線距離、v：徒歩と自転車の速いほう）：
      合計 = 徒歩(O,A) + 手続き + 自転車(A,B) + 徒歩(B,D)
           ≥ 徒歩(O,A) + 手続き + (d(A,B) + d(B,D)) を速さ v で進む時間
           ≥ 徒歩(O,A) + 手続き + d(A,D) を速さ v で進む時間   … 三角不等式
    A をこの下限の小さい順に調べ、下限が暫定の最良値を超えたら、残りの A は調べない。
    A を固定したときも 合計 ≥ 徒歩(O,A) + 手続き + 徒歩(B,D) なので、
    B を徒歩(B,D) の小さい順に調べて同様に打ち切る。

    計算量：最悪は O(貸出可能数 × 返却可能数) だが、実データでは評価する組が大幅に減る
    （計測結果は docs/engineering-notes.md §7）。
    """
    stations = list(stations)
    handling = params.rent_minutes + params.return_minutes
    fastest_kmh = max(params.walk_kmh, params.bike_kmh)

    # (下限, 徒歩(O,A)[分], 徒歩(O,A)[m], A)
    rent = []
    for a in stations:
        if can_rent(a):
            d_oa = haversine_m(origin, _point(a))
            t_oa = travel_minutes(d_oa, params.walk_kmh, params.detour_factor)
            bound = t_oa + handling + travel_minutes(haversine_m(_point(a), destination),
                                                     fastest_kmh, params.detour_factor)
            rent.append((bound, t_oa, d_oa, a))
    rent.sort(key=lambda x: (x[0], x[3].station_id))

    # (徒歩(B,D)[分], 徒歩(B,D)[m], B)
    ret = []
    for b in stations:
        if can_return(b):
            d_bd = haversine_m(_point(b), destination)
            ret.append((travel_minutes(d_bd, params.walk_kmh, params.detour_factor), d_bd, b))
    ret.sort(key=lambda x: (x[0], x[2].station_id))

    best: BikeRoute | None = None
    best_key: tuple[float, str, str] | None = None
    pairs = 0
    for bound, t_a, d_a, a in rent:
        if best_key is not None and bound > best_key[0] + _PRUNE_EPS:
            break  # 以降の A は下限が最良値を超えるので、最適解になりえない
        for t_b, d_b, b in ret:
            if best_key is not None and t_a + handling + t_b > best_key[0] + _PRUNE_EPS:
                break
            if a.station_id == b.station_id:
                continue  # 同じポートで借りて返すのは自転車に乗らないのと同じなので除外
            pairs += 1
            d_ab = haversine_m(_point(a), _point(b))
            t_ab = travel_minutes(d_ab, params.bike_kmh, params.detour_factor)
            total = t_a + params.rent_minutes + t_ab + params.return_minutes + t_b
            key = (total, a.station_id, b.station_id)  # 同値のときも結果を決定的にする
            if best_key is None or key < best_key:
                best_key = key
                best = BikeRoute(a, b, d_a, d_ab, d_b, t_a, params.rent_minutes, t_ab,
                                 params.return_minutes, t_b, total)

    return SearchResult(best, len(rent), len(ret), pairs)
