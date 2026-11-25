"""地点検索（Nominatim）のテスト。ID は evaluator の設計（PL-*）。外部には接続しない。"""

import logging
import urllib.parse

import pytest
from fakes import FakeNominatim, ManualClock, network_error
from fastapi.testclient import TestClient

from app.outbound import HttpResult, RateLimiter
from app.places import CACHE_MAX_ENTRIES, CACHE_TTL_SECONDS, PlacesClient, normalize_query
from main import app, get_places_client

SECRET = "秘密語XYZ駅"


def make_client(fake: FakeNominatim, clock: ManualClock | None = None) -> PlacesClient:
    clock = clock or ManualClock()
    return PlacesClient("https://nominatim.test", RateLimiter(clock=clock, sleep=clock.sleep),
                        fake, clock=clock, enabled=lambda: True)


@pytest.fixture
def nominatim() -> FakeNominatim:
    return FakeNominatim()


@pytest.fixture
def api(nominatim: FakeNominatim):
    places = make_client(nominatim)
    app.dependency_overrides[get_places_client] = lambda: places
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_pl1_search_and_parameters(api, nominatim):
    res = api.post("/api/places/search", json={"q": "大阪駅"})
    assert res.status_code == 200
    body = res.json()
    assert body["places"] == [{"name": "大阪駅",
                               "label": "大阪駅, 梅田3丁目, 北区, 大阪市, 日本",
                               "lat": 34.7025, "lon": 135.4959}]
    assert "Nominatim" in body["attribution"]
    params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(nominatim.calls[0]).query))
    assert params["q"] == "大阪駅"
    assert params["format"] == "jsonv2" and params["limit"] == "5"
    assert params["countrycodes"] == "jp" and params["bounded"] == "1"
    assert params["accept-language"] == "ja"
    assert params["viewbox"] == "135.35,34.78,135.65,34.55"
    assert nominatim.headers[0]["User-Agent"].startswith("ChariRoute/")


@pytest.mark.parametrize(("q", "ok"), [
    ("a", False), ("ab", True), ("x" * 64, True), ("x" * 65, False), ("", False),
    ("   ", False), ("  大阪  ", True),
])
def test_pl2_query_length(api, nominatim, q, ok):
    res = api.post("/api/places/search", json={"q": q})
    assert (res.status_code == 200) is ok
    if not ok:
        assert res.status_code == 400 and res.json()["code"] == "invalid_query"
        assert nominatim.calls == []


def test_pl2_too_long_body_is_422(api, nominatim):
    assert api.post("/api/places/search", json={"q": "x" * 201}).status_code == 422
    assert api.post("/api/places/search", json={}).status_code == 422
    assert nominatim.calls == []


def test_pl3_same_query_is_served_from_cache(api, nominatim):
    for q in ("Osaka Station", "  osaka   station ", "ＯＳＡＫＡ station"):
        assert api.post("/api/places/search", json={"q": q}).status_code == 200
    assert len(nominatim.calls) == 1


def test_normalize_query():
    assert normalize_query("  ＯＳＡＫＡ　 Station ") == "osaka station"


@pytest.mark.parametrize(("response", "code"), [
    (network_error(), "places_unavailable"),
    (HttpResult(500, None), "places_unavailable"),
    (HttpResult(200, None), "places_unavailable"),  # 不正な JSON
    (HttpResult(200, {"error": "x"}), "places_unavailable"),
    (HttpResult(429, None), "places_busy"),
])
def test_pl4_failure_is_503_and_not_cached(api, nominatim, response, code):
    nominatim.response = response
    res = api.post("/api/places/search", json={"q": "大阪駅"})
    assert res.status_code == 503 and res.json()["code"] == code
    assert "places" not in res.json()
    nominatim.response = None
    assert api.post("/api/places/search", json={"q": "大阪駅"}).status_code == 200
    assert len(nominatim.calls) == 2  # 失敗はキャッシュしない


def test_pl5_query_is_not_logged(api, nominatim, caplog):
    with caplog.at_level(logging.DEBUG):
        api.post("/api/places/search", json={"q": SECRET})
        api.post("/api/places/search", json={"q": SECRET})  # キャッシュから
        nominatim.response = network_error()
        res = api.post("/api/places/search", json={"q": SECRET + "2"})
    assert res.status_code == 503
    assert "秘密語" not in caplog.text and "XYZ" not in caplog.text
    assert "秘密語" not in res.text


def test_pl6_get_is_not_allowed(api):
    assert api.get("/api/places/search", params={"q": "大阪駅"}).status_code == 405


def test_pl7_cache_size_is_bounded(nominatim):
    c = make_client(nominatim)
    for i in range(CACHE_MAX_ENTRIES + 1):
        c.search(f"駅{i}")
    assert len(c._cache) == CACHE_MAX_ENTRIES
    c.search("駅0")  # 最も古いものは追い出されている
    assert len(nominatim.calls) == CACHE_MAX_ENTRIES + 2


def test_pl8_cache_expires_after_24_hours(nominatim):
    clock = ManualClock()
    c = make_client(nominatim, clock)
    c.search("大阪駅")
    clock.now += CACHE_TTL_SECONDS - 1
    c.search("大阪駅")
    assert len(nominatim.calls) == 1
    clock.now += 2
    c.search("大阪駅")
    assert len(nominatim.calls) == 2


def test_pl9_empty_result_is_200_and_not_cached(api, nominatim):
    nominatim.results = []
    for _ in range(2):
        res = api.post("/api/places/search", json={"q": "存在しない施設"})
        assert res.status_code == 200 and res.json()["places"] == []
    assert len(nominatim.calls) == 2


def test_results_outside_osaka_and_broken_rows_are_dropped(api, nominatim):
    nominatim.results = [
        {"name": "東京駅", "display_name": "東京駅", "lat": "35.68", "lon": "139.76"},
        {"name": "壊れた行", "lat": "x", "lon": "135.5"},
        "not a dict",
        {"display_name": "なんば駅, 中央区, 大阪市", "lat": "34.6666", "lon": "135.5008"},
    ]
    places = api.post("/api/places/search", json={"q": "なんば駅"}).json()["places"]
    assert [p["name"] for p in places] == ["なんば駅"]


def test_ob8_nominatim_limiter_is_independent_from_osrm():
    from main import get_osrm_client
    assert get_places_client.__wrapped__ is not get_osrm_client.__wrapped__
    p, o = get_places_client(), get_osrm_client()
    assert p.limiter is not o.limiter
