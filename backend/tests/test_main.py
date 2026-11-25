"""既存 API の振る舞いを固定するテスト（特性テスト）。

経路計算の本実装に入るまでは、現行のダミー応答を含めて挙動を固定する。
本実装時はダミー応答のテストを実データ前提のテストに置き換えること。
"""

import json

import pytest
from fastapi.testclient import TestClient

from main import app, handler

client = TestClient(app)


def test_health_returns_ok():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_search_returns_route_candidates():
    res = client.post("/api/routes/search", json={"origin": "梅田", "destination": "難波"})
    assert res.status_code == 200
    routes = res.json()["routes"]
    assert len(routes) >= 1
    for route in routes:
        assert isinstance(route["type"], str)
        assert isinstance(route["duration_minutes"], int)


def test_search_same_origin_and_destination_is_400():
    res = client.post("/api/routes/search", json={"origin": "梅田", "destination": "梅田"})
    assert res.status_code == 400
    assert res.json()["detail"] == "出発地と目的地が同じです"


@pytest.mark.parametrize(
    "body",
    [
        {"origin": "", "destination": "難波"},
        {"origin": "梅田", "destination": ""},
        {"origin": "梅田"},
        {},
    ],
)
def test_search_invalid_body_is_422(body):
    res = client.post("/api/routes/search", json=body)
    assert res.status_code == 422


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


def test_lambda_handler_search_via_http_api_event():
    event = _http_api_v2_event("POST", "/api/routes/search",
                               {"origin": "梅田", "destination": "難波"})
    res = handler(event, _LambdaContext())
    assert res["statusCode"] == 200
    assert "routes" in json.loads(res["body"])
