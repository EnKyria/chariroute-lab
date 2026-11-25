"""経路計算（純粋関数）のテスト。

期待値は実装を使わずに手計算する。全ポートを同じ経線（経度 135.50）上に並べると、
ハバーサイン式の距離は「地球の半径 × 緯度差（ラジアン）」に一致するので、
1 mdeg（0.001°）= 111.195 m として手で計算できる。
  徒歩：111.195 × 1.3 / 80  = 1.8069 分/mdeg
  自転車：111.195 × 1.3 / 250 = 0.5782 分/mdeg
評価シナリオは evaluator の設計（docs/engineering-notes.md）にもとづく。ID はシナリオの番号。
"""

import math
import random

import pytest

from app.routing import (
    Point,
    Station,
    haversine_m,
    search_route,
)

LON = 135.50
M_PER_MDEG = 6_371_000 * math.pi / 180 / 1000
WALK_MIN_PER_MDEG = M_PER_MDEG * 1.3 / 80
BIKE_MIN_PER_MDEG = M_PER_MDEG * 1.3 / 250
HANDLING = 2.0  # 貸出 1 分 + 返却 1 分

ORIGIN = Point(34.700, LON)
DEST = Point(34.740, LON)


def st(sid: str, lat: float, lon: float = LON, *, rent: bool = True, ret: bool = True,
       bikes: int = 5, docks: int = 5, installed: bool = True) -> Station:
    return Station(sid, f"A-{sid}.テスト", lat, lon, 10, installed, rent, ret, bikes, docks, None)


def expected_total(o_lat: float, a_lat: float, b_lat: float, d_lat: float) -> float:
    """同じ経線上の配置での合計所要時間（手計算式）。"""
    mdeg = lambda x, y: abs(x - y) * 1000  # noqa: E731
    return (mdeg(o_lat, a_lat) * WALK_MIN_PER_MDEG + mdeg(a_lat, b_lat) * BIKE_MIN_PER_MDEG
            + mdeg(b_lat, d_lat) * WALK_MIN_PER_MDEG + HANDLING)


# --- 距離 --------------------------------------------------------------------------
def test_haversine_on_meridian_matches_hand_calculation():
    assert haversine_m(Point(34.700, LON), Point(34.740, LON)) == pytest.approx(
        40 * M_PER_MDEG, rel=1e-9)


def test_haversine_known_distance_umeda_to_namba():
    # 梅田（34.7025, 135.4959）→ 難波（34.6666, 135.5008）。数 km なら平面近似とほぼ一致する：
    # 南北 35.9 mdeg × 111.195 = 3,991.9 m、東西 4.9 mdeg × 111.195 × cos(34.68°) = 448.1 m
    # → √(3991.9² + 448.1²) ≒ 4,017 m
    assert haversine_m(Point(34.7025, 135.4959), Point(34.6666, 135.5008)) == pytest.approx(
        4017, abs=5)


def test_haversine_is_symmetric_and_zero_for_same_point():
    a, b = Point(34.70, 135.49), Point(34.65, 135.52)
    assert haversine_m(a, b) == pytest.approx(haversine_m(b, a))
    assert haversine_m(a, a) == 0


# --- 組み合わせ評価 ------------------------------------------------------------------
def test_r1_nearest_rent_station_is_not_always_best():
    """R1：最寄りの貸出ポート A1 は目的地と逆方向。少し遠い A2 のほうが合計は短い。"""
    a1 = st("a1", 34.698, ret=False)  # 出発地から 2.0 mdeg（最寄り、南側）
    a2 = st("a2", 34.7025, ret=False)  # 出発地から 2.5 mdeg（北側＝目的地方向）
    b = st("b", 34.740, rent=False)
    r = search_route(ORIGIN, DEST, [a1, a2, b])
    assert r.bike is not None
    assert r.bike.rent_station.station_id == "a2"
    assert r.bike.total_minutes == pytest.approx(expected_total(34.700, 34.7025, 34.740, 34.740),
                                                 abs=0.01)
    assert r.bike.total_minutes == pytest.approx(28.20, abs=0.01)
    assert expected_total(34.700, 34.698, 34.740, 34.740) == pytest.approx(29.90, abs=0.01)


def test_r2_nearest_return_station_is_not_always_best():
    """R2：返却候補が複数あるとき、手計算で合計が最小になる返却ポートを選ぶ。"""
    a = st("a", 34.700, ret=False)
    b0 = st("b0", 34.739, rent=False)  # 目的地から 1 mdeg 手前
    b1 = st("b1", 34.7405, rent=False)  # 目的地から 0.5 mdeg 先
    r = search_route(ORIGIN, DEST, [a, b0, b1])
    t_b0 = expected_total(34.700, 34.700, 34.739, 34.740)
    t_b1 = expected_total(34.700, 34.700, 34.7405, 34.740)
    assert r.bike is not None
    best = "b0" if t_b0 < t_b1 else "b1"
    assert r.bike.return_station.station_id == best
    assert r.bike.total_minutes == pytest.approx(min(t_b0, t_b1), abs=0.01)


def test_r2b_far_return_station_wins_when_nearest_is_far_off_route():
    """目的地の最寄りの返却ポートが出発地から見て遠回りの位置にあると、2 番目が勝つ。"""
    a = st("a", 34.700, ret=False)
    near = st("near", 34.7415, rent=False)  # 目的地の 1.5 mdeg 先（最寄り）
    second = st("second", 34.738, rent=False)  # 目的地の 2.0 mdeg 手前
    r = search_route(ORIGIN, DEST, [a, near, second])
    t_near = expected_total(34.700, 34.700, 34.7415, 34.740)
    t_second = expected_total(34.700, 34.700, 34.738, 34.740)
    assert t_second < t_near  # 手計算でも 2 番目のほうが速い
    assert r.bike is not None and r.bike.return_station.station_id == "second"


def test_r3_same_station_pair_is_excluded():
    """R3：貸出・返却の両方ができるポート 1 か所で借りて返す組は採用しない。"""
    both = st("both", 34.701)
    ret_only = st("far", 34.739, rent=False)
    r = search_route(ORIGIN, DEST, [both, ret_only])
    assert r.bike is not None
    assert (r.bike.rent_station.station_id, r.bike.return_station.station_id) == ("both", "far")


@pytest.mark.parametrize("stations", [
    [st("a", 34.70, rent=False), st("b", 34.74, rent=False)],  # 貸出可能なポートがない
    [st("a", 34.70, ret=False), st("b", 34.74, ret=False)],  # 返却可能なポートがない
    [],
])
def test_r4_no_candidate_returns_none(stations):
    # PHASE 4.5：徒歩のみの経路は廃止（plan §6.3）。
    # 組がなければ bike が None になることだけを確かめる
    r = search_route(ORIGIN, DEST, stations)
    assert r.bike is None


def test_b6_single_station_both_capable_cannot_form_pair():
    r = search_route(ORIGIN, DEST, [st("only", 34.72)])
    assert r.bike is None


# --- 利用可否の判定 ------------------------------------------------------------------
@pytest.mark.parametrize("installed", [True, False])
@pytest.mark.parametrize("renting", [True, False])
@pytest.mark.parametrize("bikes", [0, 1])
def test_u1_rent_conditions_all_combinations(installed, renting, bikes):
    """U1/B1：貸出候補は is_installed かつ is_renting かつ空き自転車 > 0 だけ。"""
    target = st("target", 34.7005, ret=False, installed=installed, rent=renting, bikes=bikes)
    fallback = st("fallback", 34.6950, ret=False)  # 条件を満たさない場合に使われる遠いポート
    b = st("b", 34.740, rent=False)
    r = search_route(ORIGIN, DEST, [target, fallback, b])
    ok = installed and renting and bikes > 0
    assert r.bike is not None
    assert r.bike.rent_station.station_id == ("target" if ok else "fallback")


@pytest.mark.parametrize("installed", [True, False])
@pytest.mark.parametrize("returning", [True, False])
@pytest.mark.parametrize("docks", [0, 1])
def test_u2_return_conditions_all_combinations(installed, returning, docks):
    """U2/B2：返却候補は is_installed かつ is_returning かつ空きドック > 0 だけ。"""
    a = st("a", 34.700, ret=False)
    target = st("target", 34.7395, rent=False, installed=installed, ret=returning, docks=docks)
    fallback = st("fallback", 34.7450, rent=False)
    r = search_route(ORIGIN, DEST, [a, target, fallback])
    ok = installed and returning and docks > 0
    assert r.bike is not None
    assert r.bike.return_station.station_id == ("target" if ok else "fallback")


def test_u3_unavailable_best_station_falls_back_to_next_best():
    a_best = st("best", 34.7025, ret=False, bikes=0)  # R1 で最良だったポートを貸出不可にする
    a_next = st("next", 34.698, ret=False)
    b = st("b", 34.740, rent=False)
    r = search_route(ORIGIN, DEST, [a_best, a_next, b])
    assert r.bike is not None and r.bike.rent_station.station_id == "next"


def test_b7_unavailable_stations_near_origin_do_not_block_search():
    """B7：出発地のすぐ近くに利用不可のポートが 10 件あっても、遠くの利用可能なポートを使う。"""
    blocked = [st(f"x{i}", 34.7001 + i * 0.0001, ret=False, bikes=0) for i in range(10)]
    far = st("far", 34.690, ret=False)
    b = st("b", 34.740, rent=False)
    r = search_route(ORIGIN, DEST, [*blocked, far, b])
    assert r.bike is not None and r.bike.rent_station.station_id == "far"


# --- 最適解の保証（全探索と同じ結果） ---------------------------------------------------
def _layout_with_far_better_station(n_south: int) -> list[Station]:
    """南側に n_south 件（出発地から 2.0, 2.1, ... mdeg）、北側 3.0 mdeg に N を置く。"""
    south = [st(f"s{i:02d}", round(34.698 - i * 0.0001, 4), ret=False) for i in range(n_south)]
    north = st("n", 34.703, ret=False)
    b = st("b", 34.740, rent=False)
    return [*south, north, b]


@pytest.mark.parametrize("n_south", [9, 10, 50])
def test_b3_far_station_is_chosen_when_faster(n_south):
    """B3：N は出発地から n_south+1 番目に近いが、手計算で最速なので採用される。

    PHASE 3 の当初の実装（近い順に K=10 件に絞る）では、n_south ≥ 10 で N を見落としていた。
    全探索と同じ結果を保証する方式に変えたので、何番目に近くても採用される。
    """
    t_n = expected_total(34.700, 34.703, 34.740, 34.740)  # 28.82 分
    t_s0 = expected_total(34.700, 34.698, 34.740, 34.740)  # 29.90 分
    assert t_n < t_s0
    r = search_route(ORIGIN, DEST, _layout_with_far_better_station(n_south))
    assert r.rent_candidates == n_south + 1
    assert r.bike is not None and r.bike.rent_station.station_id == "n"
    assert r.bike.total_minutes == pytest.approx(28.82, abs=0.01)


def test_b5_single_pair_works():
    r = search_route(ORIGIN, DEST, [st("a", 34.701, ret=False), st("b", 34.739, rent=False)])
    assert (r.rent_candidates, r.return_candidates, r.pairs_evaluated) == (1, 1, 1)
    assert r.bike is not None
    assert r.bike.total_minutes == pytest.approx(expected_total(34.700, 34.701, 34.739, 34.740),
                                                 abs=0.01)


def _brute_force(origin: Point, dest: Point, stations: list[Station]):
    """仕様どおりの素朴な全探索（オラクル）。距離はテスト側の独立したハバーサイン式で計算する。"""
    def hav(lat1, lon1, lat2, lon2):
        p1, p2 = math.radians(lat1), math.radians(lat2)
        h = (math.sin((p2 - p1) / 2) ** 2
             + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
        return 2 * 6_371_000 * math.asin(math.sqrt(h))
    walk = lambda m: m * 1.3 / 80  # noqa: E731
    bike = lambda m: m * 1.3 / 250  # noqa: E731
    best = None
    for a in stations:
        if not (a.is_installed and a.is_renting and a.num_bikes_available > 0):
            continue
        for b in stations:
            if not (b.is_installed and b.is_returning and b.num_docks_available > 0):
                continue
            if a.station_id == b.station_id:
                continue
            t = (walk(hav(origin.lat, origin.lon, a.lat, a.lon)) + 1
                 + bike(hav(a.lat, a.lon, b.lat, b.lon)) + 1
                 + walk(hav(b.lat, b.lon, dest.lat, dest.lon)))
            key = (t, a.station_id, b.station_id)
            if best is None or key < best:
                best = key
    return best


@pytest.mark.parametrize("seed", range(200))
def test_result_matches_brute_force_on_random_layouts(seed):
    """ランダムな配置（大阪市付近、ポート数と利用可否もランダム）で、素朴な全探索と一致する。"""
    rng = random.Random(seed)
    n = rng.randint(0, 60)
    stations = [
        st(f"r{i:03d}", rng.uniform(34.60, 34.75), rng.uniform(135.42, 135.58),
           rent=rng.random() < 0.8, ret=rng.random() < 0.8,
           bikes=rng.choice([0, 1, 3]), docks=rng.choice([0, 1, 3]),
           installed=rng.random() < 0.95)
        for i in range(n)
    ]
    o = Point(rng.uniform(34.60, 34.75), rng.uniform(135.42, 135.58))
    d = Point(rng.uniform(34.60, 34.75), rng.uniform(135.42, 135.58))
    r = search_route(o, d, stations)
    expected = _brute_force(o, d, stations)
    if expected is None:
        assert r.bike is None
        return
    assert r.bike is not None
    assert r.bike.total_minutes == pytest.approx(expected[0], abs=1e-9)
    assert (r.bike.rent_station.station_id, r.bike.return_station.station_id) == expected[1:]


def test_pruning_reduces_evaluated_pairs():
    """打ち切りが効いていること（全組より少ない組だけを評価する）。結果は全探索と同じ。"""
    rng = random.Random(0)
    stations = [st(f"p{i:03d}", rng.uniform(34.60, 34.75), rng.uniform(135.42, 135.58))
                for i in range(200)]
    o, d = Point(34.70, 135.50), Point(34.65, 135.51)
    r = search_route(o, d, stations)
    assert r.pairs_evaluated < 200 * 199 / 10
    assert r.bike is not None
    assert r.bike.total_minutes == pytest.approx(_brute_force(o, d, stations)[0], abs=1e-9)


# --- 同値・おすすめの判定 ------------------------------------------------------------
def test_b8_tie_is_broken_deterministically_by_station_id():
    """B8：経線をはさんで東西対称の 2 ポートは合計が等しい。ID が小さいほうを採用する。"""
    east = st("east", 34.701, LON + 0.001, ret=False)
    west = st("west", 34.701, LON - 0.001, ret=False)
    b = st("b", 34.740, rent=False)
    for order in ([east, west, b], [west, east, b]):
        r = search_route(ORIGIN, DEST, order)
        assert r.bike is not None and r.bike.rent_station.station_id == "east"


# B9（おすすめの判定）は、PHASE 4.5 でおすすめの機能を廃止したため削除した（plan §6.3）。


def test_b10_short_trip_still_returns_bike():
    """B10：短い移動でも、シェアサイクルの経路を返す（徒歩との比較は PHASE 4.5 で廃止）。
    1 mdeg なら自転車 0.58 + 手続き 2 = 2.58 分。"""
    o, d = Point(34.700, LON), Point(34.701, LON)
    r = search_route(o, d, [st("a", 34.700, ret=False), st("b", 34.701, rent=False)])
    assert r.bike is not None
    assert r.bike.total_minutes == pytest.approx(BIKE_MIN_PER_MDEG + HANDLING, abs=0.01)


def test_total_is_sum_of_legs():
    r = search_route(ORIGIN, DEST, [st("a", 34.7025, ret=False), st("b", 34.7395, rent=False)])
    b = r.bike
    assert b is not None
    assert b.total_minutes == pytest.approx(b.walk_to_rent_minutes + b.rent_minutes
                                            + b.bike_minutes + b.return_minutes
                                            + b.walk_from_return_minutes)
