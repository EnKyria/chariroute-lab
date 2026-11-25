"""API（FastAPI）と Lambda 経路（Mangum）のテスト。

GBFS は依存性の差し替え（dependency_overrides）でフィクスチャに置き換える。
実ネットワークには接続しない。
PHASE 1 の特性テスト（固定のダミー応答）は、PHASE 3 で仕様を変更したため、このファイルで置き換えた。
"""

import itertools
import json
import math
from datetime import datetime

import pytest
from conftest import FIXTURE_LAST_UPDATED, FakeClock, FakeFetch, load_fixture
from fastapi.testclient import TestClient

from app.gbfs import GbfsClient, GbfsError
from app.presets import PRESETS
from main import app, get_gbfs_client, handler


@pytest.fixture
def fetch() -> FakeFetch:
    return FakeFetch()


@pytest.fixture
def client(fetch: FakeFetch):
    gbfs_client = GbfsClient(base_url="https://example.invalid/gbfs", fetch=fetch,
                             clock=FakeClock())
    app.dependency_overrides[get_gbfs_client] = lambda: gbfs_client
    yield TestClient(app)
    app.dependency_overrides.clear()


def _search(client: TestClient, o: str, d: str):
    return client.post("/api/routes/search", json={"origin_id": o, "destination_id": d})


# --- health / presets --------------------------------------------------------------
def test_health_returns_ok(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_p1_presets(client, fetch):
    res = client.get("/api/presets")
    assert res.status_code == 200
    presets = res.json()["presets"]
    assert len(presets) >= 2
    ids = [p["id"] for p in presets]
    assert len(ids) == len(set(ids))
    for p in presets:
        assert p["name"]
        assert 34.55 <= p["lat"] <= 34.78 and 135.35 <= p["lon"] <= 135.65
    assert fetch.calls == []  # プリセットの取得では GBFS に接続しない


# --- 入力エラー（V1〜V4） -----------------------------------------------------------
def test_v1_same_origin_and_destination_is_400(client):
    res = _search(client, "umeda", "umeda")
    assert res.status_code == 400
    assert res.json()["detail"] == "出発地と目的地が同じです"


@pytest.mark.parametrize(("o", "d"), [("umeda", "nowhere"), ("nowhere", "namba")])
def test_v2_unknown_preset_is_400(client, o, d):
    res = _search(client, o, d)
    assert res.status_code == 400
    assert res.json()["detail"] == "指定された地点が見つかりません"


@pytest.mark.parametrize("body", [
    {}, {"origin_id": "umeda"}, {"origin_id": "", "destination_id": "namba"},
    {"origin_id": 1, "destination_id": "namba"}, {"origin": "梅田", "destination": "難波"},
])
def test_v3_invalid_body_is_422(client, body):
    assert client.post("/api/routes/search", json=body).status_code == 422


def test_v3_no_body_is_422(client):
    assert client.post("/api/routes/search").status_code == 422


@pytest.mark.parametrize(("body", "status"), [
    ({"origin_id": "umeda", "destination_id": "umeda"}, 400),
    ({"origin_id": "umeda", "destination_id": "nowhere"}, 400),
    ({"origin_id": "umeda"}, 422),
])
def test_v4_input_errors_take_priority_over_gbfs_failure(client, fetch, body, status):
    fetch.error = GbfsError("down")
    assert client.post("/api/routes/search", json=body).status_code == status
    assert fetch.calls == []


# --- GBFS の取得失敗は 503（ダミーを返さない） ---------------------------------------
@pytest.mark.parametrize("failure", [
    "network", "broken_json", "missing_stations", "no_osaka_station", "stale",
])
def test_gbfs_failure_returns_503_without_route(client, fetch, failure):
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
    body = res.json()
    assert body == {
        "detail": "ポート情報を取得できませんでした。しばらくしてから再度お試しください"}


def test_unexpected_fetch_exception_is_not_swallowed_as_route(fetch):
    """GbfsError 以外の想定外の例外は 500 になり、経路を返さない（ダミーで取り繕わない）。"""
    fetch.error = RuntimeError("bug")
    gbfs_client = GbfsClient(base_url="https://example.invalid", fetch=fetch, clock=FakeClock())
    app.dependency_overrides[get_gbfs_client] = lambda: gbfs_client
    try:
        res = TestClient(app, raise_server_exceptions=False).post(
            "/api/routes/search", json={"origin_id": "umeda", "destination_id": "namba"})
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 500
    assert "bike_share" not in res.text


# --- 正常系の応答（P2） -------------------------------------------------------------
def test_p2_response_schema_and_data_source(client):
    res = _search(client, "umeda", "namba")
    assert res.status_code == 200
    body = res.json()
    assert body["origin"]["id"] == "umeda" and body["destination"]["id"] == "namba"
    assert body["recommended"] in ("bike_share", "walk")
    data = body["data"]
    assert datetime.fromisoformat(data["last_updated"]).timestamp() == FIXTURE_LAST_UPDATED
    assert data["last_updated"].endswith("+09:00")
    assert data["license"] == "CC BY 4.0"
    assert data["license_url"].startswith("https://creativecommons.org/licenses/by/4.0")
    assert "公共交通オープンデータ協議会" in data["attribution"]
    assert "ドコモ・バイクシェア" in data["attribution"]
    b = body["bike_share"]
    legs = (b["walk_to_rent_minutes"] + b["rent_minutes"] + b["bike_minutes"]
            + b["return_minutes"] + b["walk_from_return_minutes"])
    assert b["total_minutes"] == pytest.approx(legs, abs=0.3)  # 各区間を 0.1 分単位に丸めている


def test_cache_is_shared_between_requests(client, fetch):
    assert _search(client, "umeda", "namba").status_code == 200
    assert _search(client, "namba", "umeda").status_code == 200
    assert len(fetch.calls) == 2  # ttl 内なので 2 回目の検索では取得しない


# --- 実データのフィクスチャによる評価（F1） --------------------------------------------
# テスト側で独立に実装した計算（オラクル）。仕様の式をそのまま書き下したもの。
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
    """仕様の条件で大阪エリアの利用可能なポートを抽出する（実装の関数は使わない）。"""
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
    rent = sorted((p for p in ports if p["is_installed"] and p["is_renting"]
                   and p["num_bikes_available"] > 0),
                  key=lambda p: _hav(o["lat"], o["lon"], p["lat"], p["lon"]))
    ret = sorted((p for p in ports if p["is_installed"] and p["is_returning"]
                  and p["num_docks_available"] > 0),
                 key=lambda p: _hav(d["lat"], d["lon"], p["lat"], p["lon"]))
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
    walk_expected = _walk(_hav(o["lat"], o["lon"], d["lat"], d["lon"]))
    assert body["walk"]["total_minutes"] == pytest.approx(walk_expected, abs=0.05)

    status = {s["station_id"]: s for s in load_fixture("station_status")["data"]["stations"]}
    b = body["bike_share"]
    oracle = _oracle_best(o, d)
    if oracle is None:
        assert b is None and body["recommended"] == "walk"
        return
    assert b is not None
    # 採用したポートは実データ上で利用可能
    rs, bs = status[b["rent_station"]["station_id"]], status[b["return_station"]["station_id"]]
    assert rs["is_installed"] and rs["is_renting"] and rs["num_bikes_available"] > 0
    assert bs["is_installed"] and bs["is_returning"] and bs["num_docks_available"] > 0
    assert b["rent_station"]["station_id"] != b["return_station"]["station_id"]
    # 合計は独立に計算した全探索の最小値と一致（最適解の保証）
    assert b["total_minutes"] == pytest.approx(oracle[0], abs=0.05)
    assert body["recommended"] == ("bike_share" if oracle[0] < walk_expected else "walk")


# 代表的な地点ペアの期待値（2026-11-25 取得の実データのフィクスチャ）。
# ロジックを変えたら差分を確認する。
REPRESENTATIVE = [
    # (出発, 目的地, 推奨, 貸出ポート, 返却ポート, 自転車の合計[分], 徒歩のみ[分])
    ("umeda", "namba", "bike_share", "A-28.大阪駅", "B-16.グランドサウナ心斎橋", 30.5, 65.3),
    ("namba", "umeda", "bike_share", "B-58.クロスホテル大阪", "A-28.大阪駅", 29.6, 65.3),
    ("osaka-castle", "tennoji", "bike_share", "B-106.NTT西日本株式会社 馬場町ビル",
     "F-02.ニッセイ天王寺ビル", 35.7, 75.7),
    ("nakanoshima", "umeda", "bike_share", "A-91.大阪市役所", "A-28.大阪駅", 12.2, 18.5),
    # 近距離では差が小さい（自転車 20.2 分、徒歩 20.8 分）
    ("osaka-castle", "kyobashi", "bike_share", "G-33.ラ・フォルム天満橋イースト",
     "G-30.MFK京橋駅前ビル", 20.2, 20.8),
]


@pytest.mark.parametrize(("o", "d", "rec", "rent", "ret", "bike_total", "walk_total"),
                         REPRESENTATIVE)
def test_representative_pairs(client, o, d, rec, rent, ret, bike_total, walk_total):
    body = _search(client, o, d).json()
    assert body["recommended"] == rec
    assert body["bike_share"]["rent_station"]["name"] == rent
    assert body["bike_share"]["return_station"]["name"] == ret
    assert body["bike_share"]["total_minutes"] == pytest.approx(bike_total, abs=0.05)
    assert body["walk"]["total_minutes"] == pytest.approx(walk_total, abs=0.05)


def test_umeda_to_namba_skips_nearest_return_station(client):
    """最寄りの返却可能なポート（E-42、目的地から約 250m）ではなく、
    梅田側にある B-16（約 410m）を選ぶ。
    自転車区間の短縮が徒歩の増加を上回るため。空きドック 0 の B-58 は返却候補に入らない。"""
    body = _search(client, "umeda", "namba").json()
    ret = body["bike_share"]["return_station"]
    assert ret["name"] == "B-16.グランドサウナ心斎橋"
    assert body["bike_share"]["walk_from_return_m"] > 400
    assert ret["num_docks_available"] > 0


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


def test_lambda_handler_health_via_http_api_event():
    res = handler(_http_api_v2_event("GET", "/health"), _LambdaContext())
    assert res["statusCode"] == 200
    assert json.loads(res["body"]) == {"status": "ok"}


def test_lambda_handler_search_via_http_api_event(client):
    event = _http_api_v2_event("POST", "/api/routes/search",
                               {"origin_id": "umeda", "destination_id": "namba"})
    res = handler(event, _LambdaContext())
    assert res["statusCode"] == 200
    assert json.loads(res["body"])["bike_share"]["rent_station"]["name"] == "A-28.大阪駅"


def test_lambda_handler_returns_503_on_gbfs_failure(client, fetch):
    fetch.error = GbfsError("down")
    event = _http_api_v2_event("POST", "/api/routes/search",
                               {"origin_id": "umeda", "destination_id": "namba"})
    res = handler(event, _LambdaContext())
    assert res["statusCode"] == 503
