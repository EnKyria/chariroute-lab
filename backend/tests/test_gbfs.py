"""GBFS の取得・検証・結合・大阪エリア判定・キャッシュのテスト。実ネットワークには接続しない。"""

import http.client
import io
import socket
import urllib.error

import pytest
from conftest import FIXTURE_LAST_UPDATED, FIXTURE_NOW, FakeClock, FakeFetch, load_fixture

from app import gbfs
from app.gbfs import GbfsClient, GbfsError, is_osaka_station, parse_snapshot
from app.routing import Station


def _feed(stations: list, last_updated: int = FIXTURE_LAST_UPDATED, ttl: int = 60) -> dict:
    return {"ttl": ttl, "version": "2.3", "last_updated": last_updated,
            "data": {"stations": stations}}


def _info(sid: str, name: str = "A-1.テスト", lat: float = 34.70, lon: float = 135.50) -> dict:
    return {"station_id": sid, "name": name, "lat": lat, "lon": lon, "capacity": 10,
            "region_id": "1"}


def _status(sid: str, **kw) -> dict:
    base = {"station_id": sid, "is_installed": True, "is_renting": True, "is_returning": True,
            "num_bikes_available": 3, "num_docks_available": 4, "last_reported": 1795597000}
    return base | kw


def _station(name: str, lat: float = 34.70, lon: float = 135.50, sid: str = "1") -> Station:
    return Station(sid, name, lat, lon, 10, True, True, True, 1, 1, None)


# --- 実データのフィクスチャ ------------------------------------------------------------
def test_fixture_is_parsed_and_joined():
    snap = parse_snapshot(load_fixture("station_information"), load_fixture("station_status"),
                          FIXTURE_NOW)
    assert snap.last_updated == FIXTURE_LAST_UPDATED
    assert snap.ttl == 60
    assert snap.discarded_records == 0
    assert len(snap.stations) > 100
    ids = {s.station_id for s in snap.stations}
    # 除外ケースの実例（フィクスチャには含まれている）が結果に含まれないこと
    raw_names = {r["station_id"]: r["name"]
                 for r in load_fixture("station_information")["data"]["stations"]}
    excluded = {sid for sid, n in raw_names.items()
                if n.startswith(("【バッテリー交換のみ】", "Z-03."))
                or n == "T-27.奥武山公園(県立武道館前)"}
    assert len(excluded) == 4
    assert not (ids & excluded)
    # 状況（status）が結合されていること：実データの値をそのまま持つ
    raw_status = {r["station_id"]: r for r in load_fixture("station_status")["data"]["stations"]}
    for s in snap.stations:
        assert s.num_bikes_available == raw_status[s.station_id]["num_bikes_available"]
        assert s.num_docks_available == raw_status[s.station_id]["num_docks_available"]


# --- 大阪エリアの判定（A1〜A5） -------------------------------------------------------
@pytest.mark.parametrize(("name", "lat", "lon", "sid", "expected"), [
    ("A-96.ウメキタテラス", 34.7059, 135.4934, "1", True),
    ("B-100.Metrosa谷町六丁目South", 34.67, 135.52, "1", True),
    ("T-27.奥武山公園(県立武道館前)", 26.205, 127.673, "1", False),  # A1：那覇（同じ名前の形式）
    ("【バッテリー交換のみ】ドコモショップ福島店", 34.6949, 135.4840, "1", False),  # A2
    ("Z-03.フレスポ東大阪", 34.6918, 135.59, "7810", False),  # A3：除外リスト
    ("Z-02.フレスポ長田", 34.6797, 135.5912, "7808", False),  # A3
    ("Z-04.鶴見緑地　公園北口", 34.7164, 135.5733, "7784", True),  # Z でも大阪市内なら対象
    ("B-12 テスト", 34.70, 135.50, "1", False),  # A5：ピリオドがない
    ("b-12.テスト", 34.70, 135.50, "1", False),  # A5：小文字
    ("12.テスト", 34.70, 135.50, "1", False),  # A5：英字がない
    ("AB-12.テスト", 34.70, 135.50, "1", False),  # A5：英字 2 文字
    ("堺市役所前", 34.57, 135.48, "1", False),
])
def test_osaka_station_rule(name, lat, lon, sid, expected):
    assert is_osaka_station(_station(name, lat, lon, sid)) is expected


@pytest.mark.parametrize(("lat", "lon", "expected"), [
    (34.55, 135.50, True), (34.78, 135.50, True), (34.70, 135.35, True), (34.70, 135.65, True),
    (34.5499, 135.50, False), (34.7801, 135.50, False),
    (34.70, 135.3499, False), (34.70, 135.6501, False),
])
def test_a4_bbox_boundary_is_inclusive(lat, lon, expected):
    assert is_osaka_station(_station("A-1.テスト", lat, lon)) is expected


# --- 結合と個別レコードの不正（B11・E7・E8） -------------------------------------------
def test_b11_station_without_status_is_not_used():
    snap = parse_snapshot(_feed([_info("1"), _info("2")]), _feed([_status("1")]), FIXTURE_NOW)
    assert [s.station_id for s in snap.stations] == ["1"]


@pytest.mark.parametrize("bad_info", [
    {"station_id": "x", "name": "A-1.x", "lon": 135.5},  # lat の欠落
    {"station_id": "x", "name": "A-1.x", "lat": "34.7", "lon": 135.5},  # lat が文字列
    {"station_id": "x", "name": "A-1.x", "lat": 999, "lon": 135.5},  # 範囲外
    {"station_id": "x", "name": "A-1.x", "lat": float("nan"), "lon": 135.5},
    {"station_id": "x", "name": "A-1.x", "lat": True, "lon": 135.5},  # bool は数値として扱わない
    {"name": "A-1.x", "lat": 34.7, "lon": 135.5},  # station_id の欠落
    {"station_id": 1, "name": "A-1.x", "lat": 34.7, "lon": 135.5},  # station_id が数値
    {"station_id": "x", "lat": 34.7, "lon": 135.5},  # name の欠落
    "not-an-object",
])
def test_e7_invalid_info_record_is_discarded(bad_info):
    snap = parse_snapshot(_feed([_info("ok"), bad_info]), _feed([_status("ok"), _status("x")]),
                          FIXTURE_NOW)
    assert [s.station_id for s in snap.stations] == ["ok"]
    assert snap.discarded_records == 1


@pytest.mark.parametrize("override", [
    {"num_bikes_available": -1},
    {"num_bikes_available": "3"},
    {"num_docks_available": None},
    {"num_docks_available": 1.5},
    {"is_renting": "true"},  # Q8：真偽値でなければ捨てる（偽とはみなさない）
    {"is_returning": None},
    {"is_installed": 1},
])
def test_e7_invalid_status_record_is_discarded(override):
    snap = parse_snapshot(_feed([_info("ok"), _info("x")]),
                          _feed([_status("ok"), _status("x", **override)]), FIXTURE_NOW)
    assert [s.station_id for s in snap.stations] == ["ok"]
    assert snap.discarded_records == 1


def test_missing_status_flag_is_discarded():
    bad = _status("x")
    del bad["is_renting"]
    snap = parse_snapshot(_feed([_info("ok"), _info("x")]), _feed([_status("ok"), bad]),
                          FIXTURE_NOW)
    assert [s.station_id for s in snap.stations] == ["ok"]


def test_e8_all_records_invalid_is_error():
    with pytest.raises(GbfsError):
        parse_snapshot(_feed([{"station_id": "x"}]), _feed([_status("x")]), FIXTURE_NOW)


def test_e4_no_osaka_station_is_error():
    naha = _info("1", "T-27.奥武山公園", 26.205, 127.673)
    with pytest.raises(GbfsError):
        parse_snapshot(_feed([naha]), _feed([_status("1")]), FIXTURE_NOW)


# --- フィード全体の構造（E3・E5） -----------------------------------------------------
@pytest.mark.parametrize("broken", [
    None, [], "text", {},
    {"last_updated": FIXTURE_LAST_UPDATED},  # data がない
    {"last_updated": FIXTURE_LAST_UPDATED, "data": {}},  # data.stations がない
    {"last_updated": FIXTURE_LAST_UPDATED, "data": {"stations": {}}},  # 配列でない
    {"last_updated": FIXTURE_LAST_UPDATED, "data": []},
    {"data": {"stations": []}},  # last_updated がない
    {"last_updated": "1795597594", "data": {"stations": []}},
])
@pytest.mark.parametrize("which", ["info", "status"])
def test_e3_broken_feed_structure_is_error(broken, which):
    info, status = load_fixture("station_information"), load_fixture("station_status")
    with pytest.raises(GbfsError):
        if which == "info":
            parse_snapshot(broken, status, FIXTURE_NOW)
        else:
            parse_snapshot(info, broken, FIXTURE_NOW)


@pytest.mark.parametrize(("age", "ok"), [(900, True), (901, False), (86400, False)])
def test_e5_stale_data_is_error(age, ok):
    """Q1：2 つのフィードの last_updated のうち古いほうが 900 秒を超えて古ければエラー。"""
    info = _feed([_info("1")], last_updated=1_000_000)
    status = _feed([_status("1")], last_updated=1_000_100)
    now = 1_000_000 + age
    if ok:
        assert parse_snapshot(info, status, now).last_updated == 1_000_000
    else:
        with pytest.raises(GbfsError):
            parse_snapshot(info, status, now)


@pytest.mark.parametrize(("ahead", "ok"), [(300, True), (301, False), (10**15, False)])
def test_future_last_updated_is_error(ahead, ok):
    """時計のずれは 300 秒まで許容する。それより未来の値や極端な値は不正なデータとして扱う。"""
    now = 1_000_000
    info = _feed([_info("1")], last_updated=now)
    status = _feed([_status("1")], last_updated=now + ahead)
    if ok:
        assert parse_snapshot(info, status, now).last_updated == now
    else:
        with pytest.raises(GbfsError):
            parse_snapshot(info, status, now)


@pytest.mark.parametrize(("ttl", "expected"),
                         [(30, 30), (0, 0), (10_000, 300), ("x", 60), (-1, 60)])
def test_ttl_is_taken_from_feed_and_clamped(ttl, expected):
    snap = parse_snapshot(_feed([_info("1")], ttl=ttl), _feed([_status("1")], ttl=ttl),
                          FIXTURE_NOW)
    assert snap.ttl == expected


# --- HTTP 取得のエラー変換（E1・E2） ---------------------------------------------------
class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.mark.parametrize("error", [
    urllib.error.URLError("name resolution failed"),
    TimeoutError("timed out"),
    TimeoutError("timed out"),
    ConnectionResetError("reset"),
    urllib.error.HTTPError("u", 500, "err", {}, None),  # type: ignore[arg-type]
    urllib.error.HTTPError("u", 502, "err", {}, None),  # type: ignore[arg-type]
    urllib.error.HTTPError("u", 503, "err", {}, None),  # type: ignore[arg-type]
    urllib.error.HTTPError("u", 404, "err", {}, None),  # type: ignore[arg-type]
    http.client.IncompleteRead(b"{\"ttl\":"),  # 本文の途中で接続が切れた
    http.client.RemoteDisconnected("closed"),
])
def test_e1_fetch_errors_become_gbfs_error(monkeypatch, error):
    def fake_urlopen(url, timeout):
        raise error
    monkeypatch.setattr(gbfs.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(GbfsError):
        gbfs.fetch_json("https://example.invalid/x.json")


@pytest.mark.parametrize("body", [
    b"", b"{broken",b"<html>502 Bad Gateway</html>", b"\xff\xfe\x00"])
def test_e2_invalid_json_becomes_gbfs_error(monkeypatch, body):
    monkeypatch.setattr(gbfs.urllib.request, "urlopen", lambda url, timeout: _FakeResponse(body))
    with pytest.raises(GbfsError):
        gbfs.fetch_json("https://example.invalid/x.json")


def test_fetch_json_passes_timeout(monkeypatch):
    seen = {}

    def fake_urlopen(url, timeout):
        seen["timeout"] = timeout
        return _FakeResponse(b'{"ok": 1}')
    monkeypatch.setattr(gbfs.urllib.request, "urlopen", fake_urlopen)
    assert gbfs.fetch_json("https://example.invalid/x.json") == {"ok": 1}
    assert 0 < seen["timeout"] <= 5


# --- キャッシュ（C1〜C4） -----------------------------------------------------------
def _client(fetch: FakeFetch, clock: FakeClock) -> GbfsClient:
    return GbfsClient(base_url="https://example.invalid/gbfs", fetch=fetch, clock=clock)


def test_c1_cache_is_used_within_ttl(fake_fetch, fake_clock):
    c = _client(fake_fetch, fake_clock)
    first = c.get_snapshot()
    fake_clock.now += 59
    assert c.get_snapshot() is first
    assert len(fake_fetch.calls) == 2  # station_information と station_status を 1 回ずつ


@pytest.mark.parametrize("elapsed", [60, 61])
def test_c2_cache_expires_at_ttl(fake_fetch, fake_clock, elapsed):
    """Q4：経過時間が ttl（60 秒）以上になったら取得し直す。"""
    c = _client(fake_fetch, fake_clock)
    c.get_snapshot()
    fake_clock.now += elapsed
    c.get_snapshot()
    assert len(fake_fetch.calls) == 4


def test_c3_expired_cache_is_not_returned_on_failure(fake_fetch, fake_clock):
    c = _client(fake_fetch, fake_clock)
    c.get_snapshot()
    fake_clock.now += 61
    fake_fetch.error = GbfsError("down")
    with pytest.raises(GbfsError):
        c.get_snapshot()
    # 失敗の後も古いデータを返さない（キャッシュは破棄済み）
    fake_clock.now += 1
    with pytest.raises(GbfsError):
        c.get_snapshot()


def test_c4_failure_is_not_cached(fake_fetch, fake_clock):
    c = _client(fake_fetch, fake_clock)
    fake_fetch.error = GbfsError("down")
    with pytest.raises(GbfsError):
        c.get_snapshot()
    fake_fetch.error = None
    assert len(c.get_snapshot().stations) > 0


def test_e6_partial_failure_is_error(fake_clock):
    """E6：station_information は取得でき、station_status だけ失敗した場合。"""
    fetch = FakeFetch(status={"broken": True})
    with pytest.raises(GbfsError):
        _client(fetch, fake_clock).get_snapshot()


def test_client_uses_env_base_url(monkeypatch, fake_fetch, fake_clock):
    monkeypatch.setenv("GBFS_BASE_URL", "https://example.invalid/custom/")
    GbfsClient(fetch=fake_fetch, clock=fake_clock).get_snapshot()
    assert fake_fetch.calls[0] == "https://example.invalid/custom/station_information.json"


def test_cached_snapshot_is_not_returned_once_data_becomes_too_old():
    """ttl 内でも、データ自体が 900 秒を超えて古くなったらキャッシュを使わない（再取得する）。"""
    info, status = load_fixture("station_information"), load_fixture("station_status")
    for feed in (info, status):
        feed["ttl"] = 300
    fetch = FakeFetch(info, status)
    clock = FakeClock(FIXTURE_LAST_UPDATED + 800)  # 取得時点でデータは 800 秒前
    c = _client(fetch, clock)
    c.get_snapshot()
    clock.now += 101  # ttl（300 秒）内だが、データは 901 秒前になる
    with pytest.raises(GbfsError):  # 再取得しても同じ古いデータなので失敗する
        c.get_snapshot()
    assert len(fetch.calls) == 4


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://example.invalid/gbfs", "ftp://x"])
def test_non_https_base_url_is_rejected(url, fake_fetch):
    with pytest.raises(ValueError):
        GbfsClient(base_url=url, fetch=fake_fetch)


def test_network_guard_blocks_external_access():
    """conftest のガードが効いていること（テストから外部に接続できない）。"""
    with pytest.raises(RuntimeError):
        socket.getaddrinfo("api-public.odpt.org", 443)
