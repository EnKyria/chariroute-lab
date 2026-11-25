"""API（FastAPI）と Lambda 経路（Mangum）のテスト。

GBFS・OSRM は依存性の差し替え（dependency_overrides）でフィクスチャと偽物に置き換える。
実ネットワークには接続しない。
PHASE 4.5 で API を変更した（plan §6.11）：
- リクエストは {origin: Location, destination: Location}
  （旧形式の origin_id / destination_id は廃止）
- 応答から recommended と walk を削除（徒歩のみの経路・比較・おすすめを廃止。plan §6.3）
- 経路は道路モデル（OSRM の道路距離）。偽の OSRM の道路距離は「直線距離 × 1.3」なので、
  直線距離モデルの全探索（オラクル）と同じ値になることを確かめられる。
"""

import itertools
import json
import logging
import math
from datetime import datetime

import pytest
from conftest import FIXTURE_LAST_UPDATED, FakeClock, FakeFetch, load_fixture
from fakes import FakeOsrm, ManualClock, detour_distance, network_error, osrm_client
from fastapi.testclient import TestClient

from app.gbfs import GbfsClient, GbfsError
from app.outbound import HttpResult
from app.presets import PRESETS
from app.routing import Point
from main import app, get_gbfs_client, get_osrm_client, handler


@pytest.fixture
def fetch() -> FakeFetch:
    return FakeFetch()


@pytest.fixture
def osrm() -> FakeOsrm:
    return FakeOsrm()


@pytest.fixture
def client(fetch: FakeFetch, osrm: FakeOsrm):
    gbfs_client = GbfsClient(base_url="https://example.invalid/gbfs", fetch=fetch,
                             clock=FakeClock())
    osrm_c = osrm_client(osrm)
    app.dependency_overrides[get_gbfs_client] = lambda: gbfs_client
    app.dependency_overrides[get_osrm_client] = lambda: osrm_c
    yield TestClient(app)
    app.dependency_overrides.clear()


def _loc(x):
    return {"preset_id": x} if isinstance(x, str) else x


def _search(client: TestClient, o, d):
    return client.post("/api/routes/search", json={"origin": _loc(o), "destination": _loc(d)})


# --- health / presets --------------------------------------------------------------
def test_health_returns_ok(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_p1_presets(client, fetch, osrm):
    res = client.get("/api/presets")
    assert res.status_code == 200
    presets = res.json()["presets"]
    assert len(presets) >= 2
    ids = [p["id"] for p in presets]
    assert len(ids) == len(set(ids))
    for p in presets:
        assert p["name"]
        assert 34.55 <= p["lat"] <= 34.78 and 135.35 <= p["lon"] <= 135.65
    assert fetch.calls == [] and osrm.calls == []  # 外部に接続しない


# --- 入力エラー（V1〜V4、AP-3〜AP-7） -------------------------------------------------
GPS_UMEDA = {"lat": 34.7025, "lon": 135.4959, "source": "gps"}
MAP_NAMBA = {"lat": 34.6666, "lon": 135.5008, "source": "map"}


@pytest.mark.parametrize(("o", "d"), [
    ("umeda", "umeda"),
    (GPS_UMEDA, "umeda"),  # 座標とプリセットが同じ地点
    (GPS_UMEDA, {**GPS_UMEDA, "lat": 34.70252, "source": "map"}),  # 約 2 m
])
def test_v1_same_origin_and_destination_is_400(client, o, d):
    res = _search(client, o, d)
    assert res.status_code == 400
    assert res.json() == {"detail": "出発地と目的地が同じです", "code": "same_location"}


@pytest.mark.parametrize(("o", "d"), [("umeda", "nowhere"), ("nowhere", "namba")])
def test_v2_unknown_preset_is_400(client, o, d):
    res = _search(client, o, d)
    assert res.status_code == 400
    assert res.json()["detail"] == "指定された地点が見つかりません"


@pytest.mark.parametrize("loc", [
    {"lat": 34.549, "lon": 135.50, "source": "gps"},
    {"lat": 34.781, "lon": 135.50, "source": "gps"},
    {"lat": 34.70, "lon": 135.349, "source": "map"},
    {"lat": 35.68, "lon": 139.76, "source": "place"},  # 東京
])
def test_ap4_outside_osaka_bbox_is_400(client, osrm, loc):
    res = _search(client, loc, "namba")
    assert res.status_code == 400 and res.json()["code"] == "outside_area"
    assert osrm.calls == []


def test_ap4_inside_bbox_edge_is_ok(client):
    res = _search(client, {"lat": 34.55, "lon": 135.35, "source": "map"}, "namba")
    assert res.status_code == 200


@pytest.mark.parametrize("body", [
    {},
    {"origin": {"preset_id": "umeda"}},
    {"origin_id": "umeda", "destination_id": "namba"},  # 旧形式（廃止）
    {"origin": {"preset_id": ""}, "destination": {"preset_id": "namba"}},
    {"origin": {"lat": 34.7}, "destination": {"preset_id": "namba"}},
    {"origin": {"lat": 34.7, "lon": 135.5}, "destination": {"preset_id": "namba"}},  # source なし
    {"origin": {"lat": 34.7, "lon": 135.5, "source": "preset"},
     "destination": {"preset_id": "namba"}},
    {"origin": {"lat": 34.7, "lon": 135.5, "source": "teleport"},
     "destination": {"preset_id": "namba"}},
    {"origin": {"preset_id": "umeda", "lat": 34.7, "lon": 135.5, "source": "gps"},
     "destination": {"preset_id": "namba"}},
    {"origin": {"lat": 34.7, "lon": 135.5, "source": "gps", "name": "自宅"},
     "destination": {"preset_id": "namba"}},  # name は place のときだけ
    {"origin": {"lat": "abc", "lon": 135.5, "source": "gps"},
     "destination": {"preset_id": "namba"}},
    {"origin": {"preset_id": "umeda"}, "destination": {"preset_id": "namba"}, "x": 1},
])
def test_v3_invalid_body_is_422(client, body):
    assert client.post("/api/routes/search", json=body).status_code == 422


def test_v3_nan_coordinate_is_422(client):
    raw = ('{"origin": {"lat": NaN, "lon": 135.5, "source": "gps"},'
           ' "destination": {"preset_id": "namba"}}')
    res = client.post("/api/routes/search", content=raw,
                      headers={"Content-Type": "application/json"})
    assert res.status_code == 422


def test_v3_no_body_is_422(client):
    assert client.post("/api/routes/search").status_code == 422


@pytest.mark.parametrize(("body", "status"), [
    ({"origin": {"preset_id": "umeda"}, "destination": {"preset_id": "umeda"}}, 400),
    ({"origin": {"preset_id": "umeda"}, "destination": {"preset_id": "nowhere"}}, 400),
    ({"origin": {"preset_id": "umeda"}}, 422),
])
def test_v4_input_errors_take_priority_over_gbfs_failure(client, fetch, osrm, body, status):
    fetch.error = GbfsError("down")
    assert client.post("/api/routes/search", json=body).status_code == status
    assert fetch.calls == [] and osrm.calls == []


# --- GBFS の取得失敗は 503（ダミーを返さない） ---------------------------------------
@pytest.mark.parametrize("failure", [
    "network", "broken_json", "missing_stations", "no_osaka_station", "stale",
])
def test_gbfs_failure_returns_503_without_route(client, fetch, osrm, failure):
    if failure == "network":
        fetch.error = GbfsError("通信エラー")
    elif failure == "broken_json":
        fetch.error = GbfsError("JSON として解釈できません")
    elif failure == "missing_stations":
        fetch.status = {"last_updated": FIXTURE_LAST_UPDATED, "data": {}}
    elif failure == "no_osaka_station":
        for s in fetch.info["data"]["stations"]:
            s["lat"], s["lon"] = 26.2, 127.7  # 全ポートを那覇に移す
    elif failure == "stale":
        fetch.info["last_updated"] = fetch.status["last_updated"] = FIXTURE_LAST_UPDATED - 3600
    res = _search(client, "umeda", "namba")
    assert res.status_code == 503
    # PHASE 4.5：503 の種類を画面で区別するため、本文に code を追加した
    assert res.json() == {
        "detail": "ポート情報を取得できませんでした。しばらくしてから再度お試しください",
        "code": "gbfs_unavailable"}
    assert osrm.calls == []  # OSRM は呼ばない


def test_unexpected_fetch_exception_is_not_swallowed_as_route(fetch, osrm):
    """GbfsError 以外の想定外の例外は 500 になり、経路を返さない（ダミーで取り繕わない）。"""
    fetch.error = RuntimeError("bug")
    gbfs_client = GbfsClient(base_url="https://example.invalid", fetch=fetch, clock=FakeClock())
    app.dependency_overrides[get_gbfs_client] = lambda: gbfs_client
    app.dependency_overrides[get_osrm_client] = lambda: osrm_client(osrm)
    try:
        res = TestClient(app, raise_server_exceptions=False).post(
            "/api/routes/search",
            json={"origin": {"preset_id": "umeda"}, "destination": {"preset_id": "namba"}})
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 500
    assert "bike_share" not in res.text


# --- OSRM の失敗は 503（直線距離モデルへのフォールバックなし。AP-9） ------------------
@pytest.mark.parametrize(("service", "result"), [
    ("table", HttpResult(500, None)),
    ("table", HttpResult(400, {"code": "InvalidQuery"})),
    ("table", HttpResult(400, {"code": "TooBig"})),
    ("table", HttpResult(200, {"code": "Ok"})),
    ("table", network_error()),
    ("route", HttpResult(502, None)),
    ("route", network_error()),
])
def test_ap9_osrm_failure_is_503_without_route(client, osrm, service, result):
    osrm.override[service] = result
    res = _search(client, "umeda", "namba")
    assert res.status_code == 503
    assert res.json() == {
        "detail": "道路の経路を取得できませんでした。しばらくしてから再度お試しください",
        "code": "route_unavailable"}


def test_osrm_429_is_busy(client, osrm):
    osrm.override["table"] = HttpResult(429, None)
    res = _search(client, "umeda", "namba")
    assert res.status_code == 503 and res.json()["code"] == "route_busy"
    assert "混雑" in res.json()["detail"]


def test_ap10_search_deadline_is_503(fetch):
    """1 回の検索の締め切り（25 秒）を超えたら、残りの送信をせずに 503。"""
    clock = ManualClock()
    fake = FakeOsrm()

    def slow(url, timeout, headers):
        clock.now += 8.0  # 1 回の応答に 8 秒かかる
        return fake(url, timeout, headers)

    c = osrm_client(fake, clock)
    c._fetch = slow
    gbfs_client = GbfsClient(base_url="https://example.invalid", fetch=fetch, clock=FakeClock())
    app.dependency_overrides[get_gbfs_client] = lambda: gbfs_client
    app.dependency_overrides[get_osrm_client] = lambda: c
    try:
        res = _search(TestClient(app), "umeda", "namba")
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 503 and res.json()["code"] == "route_unavailable"
    # 送信の時刻は 1.1・9.1・17.1 秒。4 回目（25.1 秒）は締め切りの 25 秒を超えるので送らない
    assert len(fake.calls) == 3


def test_no_road_nearby_is_400(client, osrm):
    osrm.snap_override = {Point(34.6666, 135.5008): 450.0}
    res = _search(client, "umeda", MAP_NAMBA)
    assert res.status_code == 400 and res.json()["code"] == "no_road_nearby"
    assert "目的地" in res.json()["detail"]


def test_ap11_no_reachable_pair_is_200_with_null(client, osrm):
    osrm.distance = lambda *_: None
    res = _search(client, "umeda", "namba")
    assert res.status_code == 200
    body = res.json()
    assert body["bike_share"] is None
    assert "recommended" not in body and "walk" not in body


# --- 正常系の応答（P2、AP-1・AP-2） ---------------------------------------------------
def test_p2_response_schema_and_data_source(client, osrm):
    res = _search(client, "umeda", "namba")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"origin", "destination", "bike_share", "search", "data"}
    assert body["origin"] == {"name": "梅田（JR大阪駅）", "lat": 34.7025, "lon": 135.4959,
                              "source": "preset", "preset_id": "umeda"}
    data = body["data"]
    assert datetime.fromisoformat(data["last_updated"]).timestamp() == FIXTURE_LAST_UPDATED
    assert data["last_updated"].endswith("+09:00")
    assert data["license"] == "CC BY 4.0"
    assert "公共交通オープンデータ協議会" in data["attribution"]
    assert "FOSSGIS" in data["routing"]["provider"]
    assert "OpenStreetMap" in data["routing"]["map_data"]
    assert data["routing"]["fixthemap_url"] == "https://www.openstreetmap.org/fixthemap"
    b = body["bike_share"]
    assert [leg["mode"] for leg in b["legs"]] == ["walk", "bike", "walk"]
    for leg in b["legs"]:
        assert leg["distance_m"] >= 0 and leg["minutes"] >= 0
        assert len(leg["geometry"]) >= 2 and all(len(p) == 2 for p in leg["geometry"])
        assert 34.5 < leg["geometry"][0][0] < 34.8  # [lat, lon] の順
    total = sum(leg["minutes"] for leg in b["legs"]) + b["rent_minutes"] + b["return_minutes"]
    assert b["total_minutes"] == pytest.approx(total, abs=0.3)  # 各区間を 0.1 分単位に丸めている
    assert b["rent_station"]["num_bikes_available"] > 0
    assert b["return_station"]["num_docks_available"] > 0
    assert osrm.services() == [("foot", "table"), ("bike", "table"),
                               ("foot", "route"), ("bike", "route"), ("foot", "route")]
    assert 0 < body["search"]["pairs_evaluated"] <= 121


def test_coordinate_locations(client):
    res = _search(client, GPS_UMEDA, {"lat": 34.6666, "lon": 135.5008, "source": "place",
                                      "name": "なんば駅"})
    assert res.status_code == 200
    body = res.json()
    assert body["origin"]["source"] == "gps" and body["origin"]["name"] == "現在地"
    assert body["destination"]["name"] == "なんば駅"
    assert body["bike_share"] is not None


def test_ap12_logs_do_not_contain_coordinates(client, osrm, caplog):
    loc = {"lat": 34.68123, "lon": 135.51234, "source": "gps"}
    with caplog.at_level(logging.INFO):
        assert _search(client, loc, MAP_NAMBA).status_code == 200
        osrm.override["route"] = network_error()
        assert _search(client, loc, MAP_NAMBA).status_code == 503
    text = caplog.text
    assert "origin=gps destination=map" in text
    for needle in ("34.68123", "135.51234", "34.6666", "135.5008", "34.681", "135.512"):
        assert needle not in text


def test_cache_is_shared_between_requests(client, fetch):
    assert _search(client, "umeda", "namba").status_code == 200
    assert _search(client, "namba", "umeda").status_code == 200
    assert len(fetch.calls) == 2  # ttl 内なので 2 回目の検索では取得しない


# --- 実データのフィクスチャによる評価（F1） --------------------------------------------
# テスト側で独立に実装した計算（オラクル）。偽の OSRM の道路距離は「直線距離 × 1.3」なので、
# 道路モデルの結果は直線距離モデルの全探索の最小値と一致する
# （直線距離モデルの最適な組は必ず候補に入るため。plan §6.4）。
R = 6_371_000


def _hav(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def _walk(m):
    return m * 1.3 / (4.8 * 1000 / 60)


def _bike(m):
    return m * 1.3 / (15 * 1000 / 60)


def _oracle_ports():
    """仕様の条件で大阪エリアの利用可能なポートを抽出する（実装の関数は使わない）。
    名前の形式・範囲・除外 ID は app/gbfs.py の大阪エリア判定（engineering-notes §7）の複製。"""
    import re
    status = {s["station_id"]: s for s in load_fixture("station_status")["data"]["stations"]}
    ports = []
    for i in load_fixture("station_information")["data"]["stations"]:
        s = status.get(i["station_id"])
        if s is None or not re.match(r"^[A-Z]-\d+\.", i["name"]):
            continue
        if not (34.55 <= i["lat"] <= 34.78 and 135.35 <= i["lon"] <= 135.65):
            continue
        if i["station_id"] in ("7808", "7810"):
            continue
        ports.append(i | s)
    return ports


def _oracle_best(o, d):
    ports = _oracle_ports()
    rent = [p for p in ports if p["is_installed"] and p["is_renting"]
            and p["num_bikes_available"] > 0]
    ret = [p for p in ports if p["is_installed"] and p["is_returning"]
           and p["num_docks_available"] > 0]
    best = None
    for a, b in itertools.product(rent, ret):
        if a["station_id"] == b["station_id"]:
            continue
        t = (_walk(_hav(o["lat"], o["lon"], a["lat"], a["lon"])) + 1
             + _bike(_hav(a["lat"], a["lon"], b["lat"], b["lon"])) + 1
             + _walk(_hav(b["lat"], b["lon"], d["lat"], d["lon"])))
        if best is None or t < best[0]:
            best = (t, a["station_id"], b["station_id"])
    return best


PAIRS = [(o.id, d.id) for o, d in itertools.permutations(PRESETS, 2)]


@pytest.mark.parametrize(("o_id", "d_id"), PAIRS)
def test_f1_invariants_for_all_preset_pairs(client, o_id, d_id):
    body = _search(client, o_id, d_id).json()
    o, d = body["origin"], body["destination"]
    status = {s["station_id"]: s for s in load_fixture("station_status")["data"]["stations"]}
    b = body["bike_share"]
    oracle = _oracle_best(o, d)
    if oracle is None:
        assert b is None
        return
    assert b is not None
    rs, bs = status[b["rent_station"]["station_id"]], status[b["return_station"]["station_id"]]
    assert rs["is_installed"] and rs["is_renting"] and rs["num_bikes_available"] > 0
    assert bs["is_installed"] and bs["is_returning"] and bs["num_docks_available"] > 0
    assert b["rent_station"]["station_id"] != b["return_station"]["station_id"]
    # 合計は独立に計算した全探索の最小値と一致（表示は各区間を 0.1 分に丸めた和）
    assert b["total_minutes"] == pytest.approx(oracle[0], abs=0.2)


# 代表的な地点ペアの期待値（2026-11-25 取得の実データのフィクスチャ、偽の OSRM＝直線距離 × 1.3）。
# PHASE 4.5 で「推奨」と「徒歩のみ」の列を削除した（廃止した機能のため）。
# ロジックを変えたら差分を確認する。
REPRESENTATIVE = [
    # (出発, 目的地, 貸出ポート, 返却ポート, 合計[分])
    ("umeda", "namba", "A-28.大阪駅", "B-16.グランドサウナ心斎橋", 30.5),
    ("namba", "umeda", "B-58.クロスホテル大阪", "A-28.大阪駅", 29.6),
    ("osaka-castle", "tennoji", "B-106.NTT西日本株式会社 馬場町ビル",
     "F-02.ニッセイ天王寺ビル", 35.7),
    ("nakanoshima", "umeda", "A-91.大阪市役所", "A-28.大阪駅", 12.2),
    ("osaka-castle", "kyobashi", "G-33.ラ・フォルム天満橋イースト", "G-30.MFK京橋駅前ビル", 20.2),
]


@pytest.mark.parametrize(("o", "d", "rent", "ret", "bike_total"), REPRESENTATIVE)
def test_representative_pairs(client, o, d, rent, ret, bike_total):
    body = _search(client, o, d).json()
    assert body["bike_share"]["rent_station"]["name"] == rent
    assert body["bike_share"]["return_station"]["name"] == ret
    assert body["bike_share"]["total_minutes"] == pytest.approx(bike_total, abs=0.2)


def test_umeda_to_namba_skips_nearest_return_station(client):
    """最寄りの返却可能なポート（E-42）ではなく、梅田側にある B-16 を選ぶ。
    空きドック 0 の B-58 は返却候補に入らない。"""
    body = _search(client, "umeda", "namba").json()
    ret = body["bike_share"]["return_station"]
    assert ret["name"] == "B-16.グランドサウナ心斎橋"
    assert body["bike_share"]["legs"][2]["distance_m"] > 400 * 1.3
    assert ret["num_docks_available"] > 0


def test_road_detour_changes_the_chosen_return_station(client, osrm):
    """評価：B-16 への自転車の道路距離が大回り（川を渡れない）なら、別の返却ポートを選ぶ。"""
    first = _search(client, "umeda", "namba").json()["bike_share"]
    b16 = Point(first["return_station"]["lat"], first["return_station"]["lon"])

    def dist(profile, a, b):
        if profile == "bike" and b == b16:
            return 20000.0
        return detour_distance(profile, a, b)

    osrm.distance = dist
    second = _search(client, "umeda", "namba").json()["bike_share"]
    assert second["return_station"]["station_id"] != first["return_station"]["station_id"]


# --- Lambda 経路（Mangum + API Gateway HTTP API payload 2.0） ---------------------------
def _http_api_v2_event(method: str, path: str, body: dict | None = None) -> dict:
    """API Gateway HTTP API (payload format 2.0) のプロキシ統合イベントを模擬する。"""
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"host": "example.execute-api.ap-northeast-1.amazonaws.com",
                    "content-type": "application/json"},
        "requestContext": {
            "http": {"method": method, "path": path, "sourceIp": "203.0.113.1",
                     "protocol": "HTTP/1.1"},
            "stage": "$default",
        },
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
    }


class _LambdaContext:
    pass


SEARCH_BODY = {"origin": {"preset_id": "umeda"}, "destination": {"preset_id": "namba"}}


def test_lambda_handler_health_via_http_api_event():
    res = handler(_http_api_v2_event("GET", "/health"), _LambdaContext())
    assert res["statusCode"] == 200
    assert json.loads(res["body"]) == {"status": "ok"}


def test_lambda_handler_search_via_http_api_event(client):
    res = handler(_http_api_v2_event("POST", "/api/routes/search", SEARCH_BODY),
                  _LambdaContext())
    assert res["statusCode"] == 200
    assert json.loads(res["body"])["bike_share"]["rent_station"]["name"] == "A-28.大阪駅"


def test_lambda_handler_returns_503_on_gbfs_failure(client, fetch):
    fetch.error = GbfsError("down")
    res = handler(_http_api_v2_event("POST", "/api/routes/search", SEARCH_BODY),
                  _LambdaContext())
    assert res["statusCode"] == 503
