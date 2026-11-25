"""OSRM クライアントのテスト（ID は evaluator の設計 OS-*）。応答は docs/http.md の形式。"""

import pytest
from fakes import FakeOsrm, ManualClock, network_error, osrm_client

from app.osrm import OsrmClient, OsrmError, OsrmNoRoute
from app.outbound import HttpResult, RateLimiter
from app.routing import Point

A, B, C = Point(34.70, 135.50), Point(34.69, 135.51), Point(34.68, 135.52)


def test_os1_os2_table_request_and_parsing():
    fake = FakeOsrm(distance=lambda _p, a, b: 1000.0 if a != b else 0.0)
    fake.snap_override = {0: 12.5}
    t = osrm_client(fake).table("foot", [A, B, C], sources=[0, 2], destinations=[1, 2])
    assert t.distances == [[1000.0, 1000.0], [1000.0, 0.0]]
    assert t.source_snap_m == [12.5, 5.0]
    assert len(t.destination_snap_m) == 2
    url = fake.urls[0]
    assert url.startswith("https://osrm.test/routed-foot/table/v1/driving/")
    assert "135.500000,34.700000" in url  # 経度,緯度の順
    assert "annotations=distance" in url and "sources=0;2" in url and "destinations=1;2" in url


def test_os2_bike_profile_uses_bike_host():
    fake = FakeOsrm()
    osrm_client(fake).table("bike", [A, B], [0], [1])
    assert fake.urls[0].startswith("https://osrm.test/routed-bike/table/")


def test_os3_null_distance_is_none():
    fake = FakeOsrm(distance=lambda _p, a, b: None)
    t = osrm_client(fake).table("bike", [A, B], [0], [1])
    assert t.distances == [[None]]


def test_os4_route_geometry_is_lat_lon():
    fake = FakeOsrm(distance=lambda *_: 1234.5)
    r = osrm_client(fake).route("foot", A, B)
    assert r.distance_m == 1234.5
    assert r.geometry[0] == (34.70, 135.50) and r.geometry[-1] == (34.69, 135.51)
    assert "overview=full" in fake.urls[0] and "geometries=geojson" in fake.urls[0]


@pytest.mark.parametrize("status", [200, 400])
@pytest.mark.parametrize("code", ["NoRoute", "NoTable", "NoSegment"])
def test_os5_no_route_codes(status, code):
    fake = FakeOsrm()
    fake.override["table"] = HttpResult(status, {"code": code, "message": "x"})
    with pytest.raises(OsrmNoRoute):
        osrm_client(fake).table("foot", [A, B], [0], [1])


@pytest.mark.parametrize("result", [
    HttpResult(400, {"code": "InvalidQuery"}),
    HttpResult(400, {"code": "TooBig"}),
    HttpResult(500, None),
    HttpResult(502, {"message": "bad gateway"}),
    HttpResult(200, None),  # JSON として解釈できない
    HttpResult(200, {"code": "Ok"}),  # distances がない
    HttpResult(200, {"code": "Ok", "distances": [[1.0, 2.0]], "sources": [{"distance": 1}],
                     "destinations": [{"distance": 1}]}),  # 列数が違う
    HttpResult(200, {"code": "Ok", "distances": [["x"]], "sources": [{"distance": 1}],
                     "destinations": [{"distance": 1}]}),
    HttpResult(200, {"distances": [[1.0]]}),  # code がない
])
def test_os6_os7_failures_are_osrm_error(result):
    fake = FakeOsrm()
    fake.override["table"] = result
    with pytest.raises(OsrmError) as e:
        osrm_client(fake).table("foot", [A, B], [0], [1])
    assert not e.value.busy


@pytest.mark.parametrize("body", [
    {"code": "Ok", "routes": []},
    {"code": "Ok", "routes": [{"distance": 10}]},
    {"code": "Ok", "routes": [{"distance": 10, "geometry": {"coordinates": [["a", 1]]}}]},
])
def test_os7_invalid_route_is_error(body):
    fake = FakeOsrm()
    fake.override["route"] = HttpResult(200, body)
    with pytest.raises(OsrmError):
        osrm_client(fake).route("foot", A, B)


def test_os6_network_error_is_osrm_error_without_coordinates():
    fake = FakeOsrm()
    fake.override["route"] = network_error()
    with pytest.raises(OsrmError) as e:
        osrm_client(fake).route("bike", A, B)
    assert "34.7" not in str(e.value) and "135.5" not in str(e.value)
    assert len(fake.calls) == 1  # リトライしない


def test_os9_http_429_is_busy():
    fake = FakeOsrm()
    fake.override["table"] = HttpResult(429, None)
    with pytest.raises(OsrmError) as e:
        osrm_client(fake).table("foot", [A, B], [0], [1])
    assert e.value.busy


def test_os8_timeout_is_four_seconds_and_limited_by_deadline():
    fake = FakeOsrm()
    clock = ManualClock()
    client = osrm_client(fake, clock)
    client.route("foot", A, B)
    assert fake.timeouts[0] == pytest.approx(4.0)
    client.route("foot", A, B, deadline=clock.now + 1.1 + 2.0)  # 待機 1.1 秒後の残りは 2 秒
    assert fake.timeouts[1] == pytest.approx(2.0)


def test_table_timeout_is_longer_than_route_timeout():
    """自転車の Table は実測で約 9.7 秒かかったため、Table だけ 15 秒にしている。"""
    fake = FakeOsrm()
    client = osrm_client(fake)
    client.table("bike", [A, B], [0], [1])
    assert fake.timeouts[0] == pytest.approx(15.0)


def test_ob7_foot_and_bike_share_one_limiter():
    fake = FakeOsrm()
    clock = ManualClock()
    client = osrm_client(fake, clock)
    client.route("foot", A, B)
    client.route("bike", A, B)
    assert clock.sleeps == [pytest.approx(1.1), pytest.approx(1.1)]


def test_user_agent_is_sent():
    fake = FakeOsrm()
    osrm_client(fake).route("foot", A, B)
    assert fake.headers[0]["User-Agent"].startswith("ChariRoute/")


def test_url_from_env_must_be_https(monkeypatch):
    monkeypatch.setenv("OSRM_FOOT_URL", "http://insecure.test")
    with pytest.raises(ValueError):
        OsrmClient(limiter=RateLimiter())
