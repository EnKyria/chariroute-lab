"""テスト共通のフィクスチャ。

`fixtures/gbfs/` は 2026-11-25 に取得した実データの縮小版（プリセット地点の半径 1km 以内のポートと、
除外ケースの実例：那覇の T-27、東大阪の Z-03、バッテリー交換専用の拠点）。
作成手順は docs/engineering-notes.md を参照。テストから実ネットワークには接続しない。
"""

import copy
import json
import socket
from pathlib import Path
from typing import Any

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "gbfs"
FIXTURE_LAST_UPDATED = 1795597594  # フィクスチャの last_updated（2026-11-25 JST）
FIXTURE_NOW = FIXTURE_LAST_UPDATED + 30  # テストで使う「現在時刻」

_cache: dict[str, Any] = {}


def load_fixture(name: str) -> Any:
    """フィクスチャの JSON を読み込む（テストごとに書き換えられるよう深いコピーを返す）。"""
    if name not in _cache:
        _cache[name] = json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return copy.deepcopy(_cache[name])


class FakeFetch:
    """URL の末尾で station_information / station_status を返し分ける偽の取得関数。"""

    def __init__(self, info: Any = None, status: Any = None) -> None:
        self.info = load_fixture("station_information") if info is None else info
        self.status = load_fixture("station_status") if status is None else status
        self.calls: list[str] = []
        self.error: Exception | None = None  # 設定すると、以降の呼び出しで送出する

    def __call__(self, url: str) -> Any:
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        return self.info if url.endswith("station_information.json") else self.status


class FakeClock:
    def __init__(self, now: float = FIXTURE_NOW) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def fake_fetch() -> FakeFetch:
    return FakeFetch()


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


# 本番の設定に関わる環境変数。開発者のシェルに残っていても、テストの結果が変わらないように消す
_DEPLOY_ENV = ("EXTERNAL_APIS_ENABLED", "ORIGIN_VERIFY_SECRET", "AWS_LAMBDA_FUNCTION_NAME")


@pytest.fixture(autouse=True)
def _clean_deploy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _DEPLOY_ENV:
        monkeypatch.delenv(name, raising=False)


_LOOPBACK = ("127.0.0.1", "::1", "localhost")


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """テストから外部ネットワークに接続しないことを仕組みで保証する。

    外部ホストの名前解決と接続を失敗させる。ループバックは許可する
    （Windows の asyncio はスレッド間の通知に 127.0.0.1 の socket を使うため）。
    """
    real_getaddrinfo, real_connect = socket.getaddrinfo, socket.socket.connect

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if host not in _LOOPBACK:
            raise RuntimeError(f"テストから外部ネットワークに接続しようとしました: {host}")
        return real_getaddrinfo(host, *args, **kwargs)

    def connect(self: socket.socket, address: Any) -> Any:
        if isinstance(address, tuple) and address[0] not in _LOOPBACK:
            raise RuntimeError(f"テストから外部ネットワークに接続しようとしました: {address}")
        return real_connect(self, address)

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", connect)
