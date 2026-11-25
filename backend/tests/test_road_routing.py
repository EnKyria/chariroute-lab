"""道路モデル（app/road_routing.py）のテスト。ID は evaluator の設計（RR-*）。

OSRM は偽物（fakes.FakeOsrm）。道路距離は既定で「直線距離 × 1.3」、
テストごとに特定の区間だけ道路距離を上書きして、川や橋による遠回りを表す。
手計算の基準：徒歩 80 m/分、自転車 250 m/分、手続き 1 分 + 1 分。
"""

import logging

import pytest
from fakes import FakeOsrm, ManualClock, detour_distance, osrm_client

from app.osrm import OsrmError
from app.road_routing import (
    NoNearbyRoad,
    RoadParams,
    search_road_route,
    select_candidates,
)
from app.routing import Point, Station

LON = 135.50
ORIG = Point(34.700, LON)
D = Point(34.740, LON)


def st(sid: str, lat: float, lon: float = LON, *, rent: bool = True, ret: bool = True,
       bikes: int = 5, docks: int = 5) -> Station:
    return Station(sid, f"A-{sid}.テスト", lat, lon, 10, True, rent, ret, bikes, docks, None)


def pt(s: Station) -> Point:
    return Point(s.lat, s.lon)


def road(overrides: dict[tuple[str, Point, Point], float | None]):
    """指定した (profile, 起点, 終点) だけ道路距離を上書きする距離関数。"""
    def fn(profile: str, a: Point, b: Point) -> float | None:
        if (profile, a, b) in overrides:
            return overrides[(profile, a, b)]
        return detour_distance(profile, a, b)
    return fn


def run(stations, fake: FakeOsrm | None = None, **kw):
    fake = fake or FakeOsrm()
    return search_road_route(ORIG, D, stations, osrm_client(fake), **kw), fake


# --- 所要時間の計算 ----------------------------------------------------------------
def test_rr1_total_from_road_distances():
    a, b = st("a", 34.701, ret=False), st("b", 34.739, rent=False)
    fake = FakeOsrm(distance=road({("foot", ORIG, pt(a)): 400.0, ("bike", pt(a), pt(b)): 2500.0,
                                   ("foot", pt(b), D): 800.0}))
    r, _ = run([a, b], fake)
    assert r.route is not None
    assert [leg.minutes for leg in r.route.legs] == pytest.approx([5.0, 10.0, 10.0])
    assert [leg.mode for leg in r.route.legs] == ["walk", "bike", "walk"]
    assert r.route.total_minutes == pytest.approx(27.0)
    assert r.route.rent_minutes == 1.0 and r.route.return_minutes == 1.0


# --- 道路距離による選択 -------------------------------------------------------------
def test_rr2_river_crossing_station_is_not_chosen():
    """直線では最寄りの A（川の対岸）は道路で 3000 m。少し遠い B（道路 500 m）を選ぶ。"""
    a = st("a", 34.7009, ret=False)  # 直線 約 100 m
    b = st("b", 34.7036, ret=False)  # 直線 約 400 m
    ret = st("r", 34.739, rent=False)
    fake = FakeOsrm(distance=road({("foot", ORIG, pt(a)): 3000.0, ("foot", ORIG, pt(b)): 500.0}))
    r, _ = run([a, b, ret], fake)
    assert r.route is not None and r.route.rent_station.station_id == "b"


def test_rr3_farther_pair_wins_when_faster_by_road():
    near_ret = st("near", 34.7405, rent=False)
    far_ret = st("far", 34.736, rent=False)
    a = st("a", 34.700, ret=False)
    fake = FakeOsrm(distance=road({("bike", pt(a), pt(near_ret)): 9000.0}))  # 橋がなく大回り
    r, _ = run([a, near_ret, far_ret], fake)
    assert r.route is not None and r.route.return_station.station_id == "far"


@pytest.mark.parametrize(("kw", "use"), [
    ({"bikes": 0}, "rent"), ({"rent": False}, "rent"),
    ({"docks": 0}, "return"), ({"ret": False}, "return"),
])
def test_rr4_rr5_rr6_unavailable_stations_are_excluded(kw, use):
    best_rent, best_ret = st("x1", 34.7001, ret=False), st("y1", 34.7399, rent=False)
    other_rent, other_ret = st("x2", 34.698, ret=False), st("y2", 34.742, rent=False)
    if use == "rent":
        best_rent = st("x1", 34.7001, ret=False, **kw)
    else:
        best_ret = st("y1", 34.7399, rent=False, **kw)
    r, _ = run([best_rent, best_ret, other_rent, other_ret])
    assert r.route is not None
    chosen = r.route.rent_station if use == "rent" else r.route.return_station
    assert chosen.station_id.endswith("2")


def test_rr7_one_bike_and_one_dock_are_enough():
    r, _ = run([st("a", 34.701, ret=False, bikes=1), st("b", 34.739, rent=False, docks=1)])
    assert r.route is not None


def test_rr8_same_station_pair_is_not_evaluated():
    both = st("g", 34.720)  # 貸出・返却の両方の候補に入る
    a, b = st("a", 34.701, ret=False), st("b", 34.739, rent=False)
    fake = FakeOsrm(distance=road({("bike", pt(both), pt(both)): 0.0}))
    r, _ = run([both, a, b], fake)
    assert r.route is not None
    assert r.route.rent_station.station_id != r.route.return_station.station_id


# --- 候補の数と重複 -----------------------------------------------------------------
def grid(n: int) -> list[Station]:
    return [st(f"p{i:02d}", 34.700 + 0.0013 * i) for i in range(n)]


def test_rr9_candidates_are_capped_and_requests_are_five():
    stations = grid(31)
    r, fake = run(stations)
    assert r.rent_candidates <= 11 and r.return_candidates <= 11
    assert r.pairs_evaluated <= 121
    assert fake.services() == [("foot", "table"), ("bike", "table"),
                               ("foot", "route"), ("bike", "route"), ("foot", "route")]
    foot_points, bike_points = fake.calls[0][2], fake.calls[1][2]
    assert foot_points <= 24 and bike_points <= 22


def test_rr10_linear_best_pair_is_added_without_duplicates():
    stations = grid(31)
    rent, ret = select_candidates(ORIG, D, stations)
    assert len({s.station_id for s in rent}) == len(rent)
    assert len({s.station_id for s in ret}) == len(ret)
    assert 10 <= len(rent) <= 11 and 10 <= len(ret) <= 11


def test_rr10b_linear_best_outside_nearest_ten_is_added():
    """直線距離モデルの最適な貸出ポートが、近い順で 11 件目になる配置。"""
    # 出発地の南（目的地と逆方向）約 300 m に 10 件。目的地の方向の約 311 m に ahead
    near = [st(f"n{i}", 34.6973, LON + 0.00001 * i, ret=False) for i in range(10)]
    ahead = st("ahead", 34.7028, ret=False)
    b = st("b", 34.740, rent=False)
    rent, _ = select_candidates(ORIG, D, [*near, ahead, b])
    ids = [s.station_id for s in rent]
    assert len(ids) == 11 and "ahead" in ids


# --- 到達できない組 -----------------------------------------------------------------
def test_rr11_unreachable_rent_station_is_skipped():
    a = st("a", 34.701, ret=False)
    a2 = st("a2", 34.703, ret=False)
    b = st("b", 34.739, rent=False)
    fake = FakeOsrm(distance=road({("foot", ORIG, pt(a)): None}))
    r, _ = run([a, a2, b], fake)
    assert r.route is not None and r.route.rent_station.station_id == "a2"


def test_rr12_unreachable_bike_pair_only_excludes_that_pair():
    a = st("a", 34.701, ret=False)
    b1, b2 = st("b1", 34.7395, rent=False), st("b2", 34.735, rent=False)
    fake = FakeOsrm(distance=road({("bike", pt(a), pt(b1)): None}))
    r, _ = run([a, b1, b2], fake)
    assert r.route is not None and r.route.return_station.station_id == "b2"


@pytest.mark.parametrize("case", ["all_null", "no_stations", "single_station", "no_table"])
def test_rr13_no_pair_returns_none(case):
    stations = [st("a", 34.701, ret=False), st("b", 34.739, rent=False)]
    fake = FakeOsrm()
    if case == "all_null":
        fake.distance = lambda *_: None
    elif case == "no_stations":
        stations = []
    elif case == "single_station":
        stations = [st("only", 34.72)]
    else:
        from app.outbound import HttpResult
        fake.override["table"] = HttpResult(400, {"code": "NoTable"})
    r, _ = run(stations, fake)
    assert r.route is None
    assert not any(s == "route" for _, s in fake.services())


def test_rr14_tie_is_broken_by_station_id():
    east = st("east", 34.701, LON + 0.001, ret=False)
    west = st("west", 34.701, LON - 0.001, ret=False)
    b = st("b", 34.740, rent=False)
    for order in ([east, west, b], [west, east, b]):
        r, _ = run(order)
        assert r.route is not None and r.route.rent_station.station_id == "east"


# --- Table と Route の整合 ----------------------------------------------------------
def test_rr15_display_uses_route_distance_and_does_not_reselect(caplog):
    a, b = st("a", 34.701, ret=False), st("b", 34.739, rent=False)
    fake = FakeOsrm(distance=road({("bike", pt(a), pt(b)): 2500.0}))
    fake.route_distance = road({("bike", pt(a), pt(b)): 2600.0})
    with caplog.at_level(logging.WARNING, logger="chariroute.road"):
        r, _ = run([a, b], fake)
    assert r.route is not None
    assert r.route.legs[1].distance_m == 2600.0
    assert r.route.legs[1].minutes == pytest.approx(10.4)
    assert len(fake.calls) == 5
    assert "差が大きい" not in caplog.text  # 100 m・4% は警告のしきい値の内側


def test_rr18_large_mismatch_is_logged_without_coordinates(caplog):
    a, b = st("a", 34.701, ret=False), st("b", 34.739, rent=False)
    fake = FakeOsrm(distance=road({("bike", pt(a), pt(b)): 2500.0}))
    fake.route_distance = road({("bike", pt(a), pt(b)): 3000.0})
    with caplog.at_level(logging.WARNING, logger="chariroute.road"):
        run([a, b], fake)
    assert "差が大きい" in caplog.text and "mode=bike" in caplog.text
    assert "34.7" not in caplog.text and "135.5" not in caplog.text


def test_rr19_zero_distance_leg_is_fine():
    a, b = st("a", ORIG.lat, ret=False), st("b", 34.739, rent=False)
    fake = FakeOsrm(distance=road({("foot", ORIG, pt(a)): 0.0}))
    r, _ = run([a, b], fake)
    assert r.route is not None and r.route.legs[0].minutes == 0.0


def test_rr21_not_worse_than_linear_best_pair_by_road():
    stations = grid(31)
    r, _ = run(stations)
    rent, ret = select_candidates(ORIG, D, stations)
    assert r.route is not None
    assert r.route.rent_station in rent and r.route.return_station in ret


# --- スナップ距離と障害 -------------------------------------------------------------
@pytest.mark.parametrize(("point", "which"), [(ORIG, "origin"), (D, "destination")])
def test_rr17_far_from_road_is_no_nearby_road(point, which):
    stations = grid(31)
    fake = FakeOsrm()
    fake.snap_override = {point: 301.0}
    with pytest.raises(NoNearbyRoad) as e:
        run(stations, fake)
    assert e.value.which == which


def test_rr17_snap_exactly_300_is_allowed():
    fake = FakeOsrm()
    fake.snap_override = {ORIG: 300.0, D: 300.0}
    r, _ = run([st("a", 34.701, ret=False), st("b", 34.739, rent=False)], fake)
    assert r.route is not None


def test_osrm_failure_propagates():
    from fakes import network_error
    fake = FakeOsrm()
    fake.override["route"] = network_error()
    with pytest.raises(OsrmError):
        run([st("a", 34.701, ret=False), st("b", 34.739, rent=False)], fake)


def test_deadline_exceeded_raises_and_stops_sending():
    clock = ManualClock()
    fake = FakeOsrm()
    client = osrm_client(fake, clock)
    stations = [st("a", 34.701, ret=False), st("b", 34.739, rent=False)]
    with pytest.raises(OsrmError):
        search_road_route(ORIG, D, stations, client, deadline=clock.now + 3.0)
    assert len(fake.calls) == 2  # 1.1 秒 × 2 の後、3 回目の待機で締め切りを超える


def test_custom_speed_params():
    a, b = st("a", 34.701, ret=False), st("b", 34.739, rent=False)
    fake = FakeOsrm(distance=road({("bike", pt(a), pt(b)): 3000.0}))
    r = search_road_route(ORIG, D, [a, b], osrm_client(fake), params=RoadParams(bike_kmh=18.0))
    assert r.route is not None and r.route.legs[1].minutes == pytest.approx(10.0)
