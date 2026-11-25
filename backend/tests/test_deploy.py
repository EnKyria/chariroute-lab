"""本番（AWS）向けの設定のテスト（PHASE 6、plan §7.3・§7.6・§7.8 の手順 1）。

- 外部 API（FOSSGIS OSRM・Nominatim）の有効・無効のフラグ：既定は無効。無効なら送信せずに 503。
- CloudFront の共有シークレット（X-Origin-Verify）の検証：Lambda 上では必須。欠けていれば 403。
- API の応答は Cache-Control: no-store
  （座標・検索語を含みうるので、CloudFront でキャッシュしない）。

外部 API の有効・無効は、各クライアントの既定（環境変数を読む）のまま使う。
環境変数は conftest の `_clean_deploy_env` が毎回消すので、テストの中で明示的に設定する。
"""

import json
import logging

import pytest
from conftest import FakeClock, FakeFetch
from fakes import BIKE_URL, FOOT_URL, FakeNominatim, FakeOsrm, ManualClock
from fastapi.testclient import TestClient

from app.gbfs import GbfsClient
from app.osrm import OsrmClient, OsrmError
from app.outbound import RateLimiter, external_apis_enabled
from app.places import PlacesClient, PlacesError
from app.routing import Point
from app.security import MIN_SECRET_LEN
from main import app, get_gbfs_client, get_osrm_client, get_places_client, handler

SECRET = "s" * MIN_SECRET_LEN + "-Test0123"  # ヘッダーの値は ASCII だけ
A, B = Point(34.70, 135.49), Point(34.67, 135.50)
SEARCH = {"origin": {"preset_id": "umeda"}, "destination": {"preset_id": "namba"}}


def default_osrm(fake: FakeOsrm, clock: ManualClock) -> OsrmClient:
    """enabled を渡さない（本番と同じく環境変数で決まる）クライアント。"""
    return OsrmClient(FOOT_URL, BIKE_URL, RateLimiter(clock=clock, sleep=clock.sleep), fake)


def default_places(fake: FakeNominatim, clock: ManualClock) -> PlacesClient:
    return PlacesClient("https://nominatim.test", RateLimiter(clock=clock, sleep=clock.sleep),
                        fake, clock=clock)


@pytest.fixture
def gbfs_fetch() -> FakeFetch:
    return FakeFetch()


@pytest.fixture
def osrm() -> FakeOsrm:
    return FakeOsrm()


@pytest.fixture
def nominatim() -> FakeNominatim:
    return FakeNominatim()


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()


@pytest.fixture
def api(gbfs_fetch, osrm, nominatim, clock):
    gbfs = GbfsClient(base_url="https://example.invalid/gbfs", fetch=gbfs_fetch,
                      clock=FakeClock())
    o, p = default_osrm(osrm, clock), default_places(nominatim, clock)
    app.dependency_overrides[get_gbfs_client] = lambda: gbfs
    app.dependency_overrides[get_osrm_client] = lambda: o
    app.dependency_overrides[get_places_client] = lambda: p
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- 外部 API の有効・無効のフラグ --------------------------------------------------------
@pytest.mark.parametrize("value", ["true", "TRUE", "True", " true ", "true\n"])
def test_flag_enabled_only_by_explicit_true(monkeypatch, value):
    monkeypatch.setenv("EXTERNAL_APIS_ENABLED", value)
    assert external_apis_enabled() is True


@pytest.mark.parametrize("value", ["", "1", "yes", "on", "enabled", "ture", "false", "0",
                                   "true false", "\"true\""])
def test_flag_disabled_for_anything_else(monkeypatch, value):
    monkeypatch.setenv("EXTERNAL_APIS_ENABLED", value)
    assert external_apis_enabled() is False


def test_flag_disabled_when_unset():
    assert external_apis_enabled() is False


def test_osrm_disabled_by_default_sends_nothing_and_does_not_wait(osrm, clock):
    c = default_osrm(osrm, clock)
    with pytest.raises(OsrmError) as e:
        c.route("foot", A, B)
    assert e.value.disabled is True and e.value.busy is False
    with pytest.raises(OsrmError):
        c.table("bike", [A, B], [0], [1])
    assert osrm.calls == []
    assert c.limiter.sent == 0
    assert clock.sleeps == []  # リミッターの待ち時間も使わない


def test_osrm_flag_is_checked_on_every_send(monkeypatch, osrm, clock):
    """実行中に無効へ切り替えたら、次の送信から止まる（緊急停止の手段の 1 つ。plan §7.9）。"""
    c = default_osrm(osrm, clock)
    monkeypatch.setenv("EXTERNAL_APIS_ENABLED", "true")
    c.route("foot", A, B)
    monkeypatch.setenv("EXTERNAL_APIS_ENABLED", "false")
    with pytest.raises(OsrmError) as e:
        c.route("foot", A, B)
    assert e.value.disabled is True
    assert len(osrm.calls) == 1


def test_places_disabled_by_default_sends_nothing(nominatim, clock):
    c = default_places(nominatim, clock)
    with pytest.raises(PlacesError) as e:
        c.search("大阪駅")
    assert e.value.disabled is True
    assert nominatim.calls == [] and c.limiter.sent == 0


def test_places_disabled_does_not_serve_cache(monkeypatch, nominatim, clock):
    """無効の間はキャッシュも返さない（無効 = 地点検索の機能を止める、と一貫させる）。"""
    c = default_places(nominatim, clock)
    monkeypatch.setenv("EXTERNAL_APIS_ENABLED", "true")
    assert c.search("大阪駅")
    monkeypatch.delenv("EXTERNAL_APIS_ENABLED")
    with pytest.raises(PlacesError):
        c.search("大阪駅")
    assert len(nominatim.calls) == 1


def test_api_route_search_disabled_is_503_after_gbfs(api, gbfs_fetch, osrm):
    res = api.post("/api/routes/search", json=SEARCH)
    assert res.status_code == 503
    body = res.json()
    assert body["code"] == "route_disabled"
    assert "停止" in body["detail"]
    assert "bike_share" not in body and "legs" not in body  # ダミーの経路を返さない
    assert gbfs_fetch.calls  # GBFS（ODPT）は取得する（AWS 上の疎通確認に使う。plan §7.8 の手順 9）
    assert osrm.calls == []


def test_api_places_search_disabled_is_503(api, nominatim):
    res = api.post("/api/places/search", json={"q": "大阪駅"})
    assert res.status_code == 503
    assert res.json()["code"] == "places_disabled"
    assert "places" not in res.json()
    assert nominatim.calls == []


def test_api_route_search_works_when_explicitly_enabled(monkeypatch, api, osrm):
    monkeypatch.setenv("EXTERNAL_APIS_ENABLED", "true")
    res = api.post("/api/routes/search", json=SEARCH)
    assert res.status_code == 200
    assert res.json()["bike_share"] is not None
    assert osrm.calls


def test_presets_and_health_work_while_disabled(api):
    assert api.get("/health").status_code == 200
    assert api.get("/api/presets").status_code == 200


# --- CloudFront の共有シークレット ------------------------------------------------------
def test_origin_check_off_locally_without_secret(api):
    """ローカル（Lambda でなく、シークレットも未設定）では検証しない。"""
    assert api.get("/api/presets").status_code == 200


@pytest.mark.parametrize("path", ["/health", "/api/presets", "/docs", "/openapi.json",
                                  "/no-such-path"])
def test_lambda_without_secret_rejects_everything(monkeypatch, api, path):
    """Lambda 上でシークレットを設定し忘れたら、全てを 403 にする（安全側）。"""
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "chariroute-api")
    res = api.get(path, headers={"X-Origin-Verify": "anything"})
    assert res.status_code == 403
    assert res.json() == {"detail": "アクセスが許可されていません", "code": "forbidden"}


def test_lambda_with_short_secret_rejects_even_matching_header(monkeypatch, api):
    short = "x" * (MIN_SECRET_LEN - 1)
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "chariroute-api")
    monkeypatch.setenv("ORIGIN_VERIFY_SECRET", short)
    assert api.get("/api/presets", headers={"X-Origin-Verify": short}).status_code == 403


@pytest.mark.parametrize("headers", [{}, {"X-Origin-Verify": ""},
                                     {"X-Origin-Verify": SECRET[:-1]},
                                     {"X-Origin-Verify": SECRET + "x"},
                                     {"X-Origin-Verify": SECRET.upper()},
                                     {"Authorization": SECRET}])
def test_secret_mismatch_is_403(monkeypatch, api, headers):
    monkeypatch.setenv("ORIGIN_VERIFY_SECRET", SECRET)
    assert api.get("/api/presets", headers=headers).status_code == 403


def test_secret_match_is_allowed_and_header_name_is_case_insensitive(monkeypatch, api):
    monkeypatch.setenv("ORIGIN_VERIFY_SECRET", SECRET)
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "chariroute-api")
    assert api.get("/api/presets", headers={"X-Origin-Verify": SECRET}).status_code == 200
    assert api.get("/health", headers={"x-origin-verify": SECRET}).status_code == 200


def test_rejected_request_does_not_reach_gbfs_or_external_apis(monkeypatch, api, gbfs_fetch,
                                                               osrm):
    monkeypatch.setenv("ORIGIN_VERIFY_SECRET", SECRET)
    monkeypatch.setenv("EXTERNAL_APIS_ENABLED", "true")
    res = api.post("/api/routes/search", json=SEARCH)
    assert res.status_code == 403
    assert gbfs_fetch.calls == [] and osrm.calls == []


def test_secret_is_not_in_logs_or_response(monkeypatch, api, caplog):
    monkeypatch.setenv("ORIGIN_VERIFY_SECRET", SECRET)
    caplog.set_level(logging.DEBUG)
    res = api.get("/api/presets", headers={"X-Origin-Verify": SECRET + "x"})
    assert SECRET not in res.text and SECRET not in caplog.text
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "chariroute-api")
    monkeypatch.setenv("ORIGIN_VERIFY_SECRET", "short-secret-value")
    res = api.get("/api/presets", headers={"X-Origin-Verify": "short-secret-value"})
    assert "short-secret-value" not in res.text and "short-secret-value" not in caplog.text
    assert "ORIGIN_VERIFY_SECRET" in caplog.text  # 原因は分かるように、名前だけ出す


# --- Cache-Control -------------------------------------------------------------------
def test_no_store_on_success_error_and_forbidden(monkeypatch, api):
    assert api.get("/api/presets").headers["cache-control"] == "no-store"
    assert api.post("/api/routes/search", json=SEARCH).headers["cache-control"] == "no-store"
    assert api.post("/api/routes/search", json={}).headers["cache-control"] == "no-store"  # 422
    monkeypatch.setenv("ORIGIN_VERIFY_SECRET", SECRET)
    assert api.get("/api/presets").headers["cache-control"] == "no-store"  # 403


def test_no_store_and_generic_body_on_unhandled_500(gbfs_fetch):
    """想定外の例外でも、本文に内容を出さず、no-store を付ける。"""
    def broken():
        raise RuntimeError("内部の詳細 34.70,135.49")

    app.dependency_overrides[get_gbfs_client] = broken
    try:
        res = TestClient(app, raise_server_exceptions=False).post("/api/routes/search",
                                                                  json=SEARCH)
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 500
    assert res.headers["cache-control"] == "no-store"
    assert res.json() == {"detail": "サーバーでエラーが発生しました", "code": "internal_error"}


def test_app_cache_control_is_overridden_with_no_store(monkeypatch, api):
    """アプリが別の Cache-Control を付けても、no-store に置き換える（重複させない）。"""
    res = api.get("/openapi.json")
    assert res.headers.get_list("cache-control") == ["no-store"]


@pytest.mark.parametrize("value", [" " * 40, chr(9) * 40, " " * 20 + "x" * 20])
def test_lambda_with_blank_or_short_stripped_secret_is_403(monkeypatch, api, value):
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "chariroute-api")
    monkeypatch.setenv("ORIGIN_VERIFY_SECRET", value)
    assert api.get("/api/presets", headers={"X-Origin-Verify": value.strip() or "x"}
                   ).status_code == 403


def test_secret_with_surrounding_whitespace_is_trimmed(monkeypatch, api):
    monkeypatch.setenv("ORIGIN_VERIFY_SECRET", "  " + SECRET + chr(10))
    assert api.get("/api/presets", headers={"X-Origin-Verify": SECRET}).status_code == 200


# --- Lambda 経路（Mangum + HTTP API payload 2.0）------------------------------------------
def _event(method: str, path: str, headers: dict[str, str], body: dict | None = None) -> dict:
    return {
        "version": "2.0", "routeKey": "$default", "rawPath": path, "rawQueryString": "",
        "headers": {"host": "example.execute-api.ap-northeast-1.amazonaws.com",
                    "content-type": "application/json", **headers},
        "requestContext": {"http": {"method": method, "path": path, "sourceIp": "203.0.113.1",
                                    "protocol": "HTTP/1.1"}, "stage": "$default"},
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
    }


class _Ctx:
    pass


def test_lambda_handler_requires_origin_secret(monkeypatch, api, gbfs_fetch):
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "chariroute-api")
    monkeypatch.setenv("ORIGIN_VERIFY_SECRET", SECRET)
    res = handler(_event("GET", "/api/presets", {}), _Ctx())
    assert res["statusCode"] == 403
    res = handler(_event("GET", "/api/presets", {"x-origin-verify": SECRET}), _Ctx())
    assert res["statusCode"] == 200
    assert res["headers"]["cache-control"] == "no-store"
    # 本番の既定（外部 API は無効）：GBFS は取得し、経路は 503（route_disabled）
    res = handler(_event("POST", "/api/routes/search", {"x-origin-verify": SECRET}, SEARCH),
                  _Ctx())
    assert res["statusCode"] == 503
    assert json.loads(res["body"])["code"] == "route_disabled"
    assert gbfs_fetch.calls
