"""ドコモ・バイクシェア GBFS（ODPT 公開フィード）の取得・検証・結合・キャッシュ。

方針：
- 取得や構造の検証に失敗したら GbfsError を送出する（呼び出し側で 503 にする）。
  ダミー値や期限切れのキャッシュを代わりに返すことはしない。
- 個々のポートのレコードが壊れている場合は、そのポートだけを捨てる（全体を失敗にはしない）。
"""

import http.client
import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.routing import Station

DEFAULT_BASE_URL = "https://api-public.odpt.org/api/v4/gbfs/docomo-cycle"
HTTP_TIMEOUT_SECONDS = 4.0  # 2 ファイルを順に取得しても Lambda のタイムアウト（10 秒）に収まる値
DEFAULT_TTL_SECONDS = 60
MAX_TTL_SECONDS = 300
MAX_DATA_AGE_SECONDS = 900  # フィードの last_updated がこれより古ければ「古すぎるデータ」として扱う
MAX_CLOCK_SKEW_SECONDS = 300  # last_updated が現在より未来すぎる場合も不正なデータとして扱う

# --- 大阪エリアの判定 -------------------------------------------------------------
# GBFS には地域を判定できる項目がない（system_regions は 404、region_id は全国にまたがる）。
# 実データの調査（2026-11-25）から、大阪市のポートは名前が「A-96.」のような
# 「英字 1 文字-番号.」で始まることがわかった。同じ形式は那覇・長野などにもあるため、範囲でも絞る。
# 詳細と仮定は docs/engineering-notes.md を参照。
OSAKA_NAME_PATTERN = re.compile(r"^[A-Z]-\d+\.")
OSAKA_BBOX = (34.55, 34.78, 135.35, 135.65)  # (緯度の最小, 最大, 経度の最小, 最大)
# 名前の形式と範囲の条件を満たすが、大阪市外（東大阪市）にあると判断したポート。
# 大阪エリアの外には返却できないため、安全側に倒して除外する。
EXCLUDED_STATION_IDS = frozenset({"7808", "7810"})  # Z-02.フレスポ長田、Z-03.フレスポ東大阪


class GbfsError(Exception):
    """GBFS の取得・検証に失敗した（API では 503 にする）。"""


@dataclass(frozen=True)
class Snapshot:
    stations: tuple[Station, ...]  # 大阪エリアのポートだけ
    last_updated: int  # 2 つのフィードの last_updated のうち古いほう（UNIX 秒）
    ttl: int
    discarded_records: int  # 不正なため捨てたレコードの数


def is_osaka_station(s: Station) -> bool:
    lat_min, lat_max, lon_min, lon_max = OSAKA_BBOX
    return (
        OSAKA_NAME_PATTERN.match(s.name) is not None
        and lat_min <= s.lat <= lat_max
        and lon_min <= s.lon <= lon_max
        and s.station_id not in EXCLUDED_STATION_IDS
    )


# --- 取得 ---------------------------------------------------------------------------
def fetch_json(url: str, timeout: float = HTTP_TIMEOUT_SECONDS) -> Any:
    """URL から JSON を取得する。失敗は GbfsError にまとめる。"""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:
            body = res.read()
    except urllib.error.HTTPError as e:
        raise GbfsError(f"HTTP {e.code}: {url}") from e
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as e:
        # http.client.HTTPException：本文の途中で接続が切れた（IncompleteRead）など
        raise GbfsError(f"通信エラー: {url}: {e!r}") from e
    try:
        return json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise GbfsError(f"JSON として解釈できません: {url}") from e


# --- 検証 ---------------------------------------------------------------------------
def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_number(v: Any) -> bool:
    return (_is_int(v) or isinstance(v, float)) and math.isfinite(v)


def _feed_stations(feed: Any, name: str) -> tuple[list[Any], int, int]:
    """フィード全体の構造を検証し、(stations, last_updated, ttl) を返す。"""
    if not isinstance(feed, dict):
        raise GbfsError(f"{name}: トップレベルがオブジェクトではありません")
    last_updated = feed.get("last_updated")
    if not _is_int(last_updated) or last_updated <= 0:
        raise GbfsError(f"{name}: last_updated が不正です")
    data = feed.get("data")
    stations = data.get("stations") if isinstance(data, dict) else None
    if not isinstance(stations, list):
        raise GbfsError(f"{name}: data.stations がありません")
    ttl = feed.get("ttl")
    if not _is_int(ttl) or ttl < 0:
        ttl = DEFAULT_TTL_SECONDS
    return stations, last_updated, min(ttl, MAX_TTL_SECONDS)


def _parse_info(r: Any) -> dict[str, Any] | None:
    if not isinstance(r, dict):
        return None
    sid, name, lat, lon = r.get("station_id"), r.get("name"), r.get("lat"), r.get("lon")
    if not (isinstance(sid, str) and sid and isinstance(name, str)):
        return None
    if not (_is_number(lat) and _is_number(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    capacity = r.get("capacity")
    return {"station_id": sid, "name": name, "lat": float(lat), "lon": float(lon),
            "capacity": capacity if _is_int(capacity) and capacity >= 0 else None}


def _parse_status(r: Any) -> dict[str, Any] | None:
    if not isinstance(r, dict) or not (isinstance(r.get("station_id"), str) and r["station_id"]):
        return None
    flags = ("is_installed", "is_renting", "is_returning")
    counts = ("num_bikes_available", "num_docks_available")
    if not all(isinstance(r.get(k), bool) for k in flags):
        return None
    if not all(_is_int(r.get(k)) and r[k] >= 0 for k in counts):
        return None
    last_reported = r.get("last_reported")
    return {"station_id": r["station_id"], **{k: r[k] for k in flags + counts},
            "last_reported": last_reported if _is_int(last_reported) else None}


def check_freshness(last_updated: int, now: float) -> None:
    if now - last_updated > MAX_DATA_AGE_SECONDS:
        raise GbfsError(f"データが古すぎます（last_updated={last_updated}）")


def parse_snapshot(info_feed: Any, status_feed: Any, now: float) -> Snapshot:
    """2 つのフィードを検証・結合し、大阪エリアのポートだけを返す。"""
    info_rows, info_updated, info_ttl = _feed_stations(info_feed, "station_information")
    status_rows, status_updated, status_ttl = _feed_stations(status_feed, "station_status")

    last_updated = min(info_updated, status_updated)
    check_freshness(last_updated, now)
    if max(info_updated, status_updated) > now + MAX_CLOCK_SKEW_SECONDS:
        raise GbfsError("last_updated が未来の時刻です")

    discarded = 0
    statuses: dict[str, dict[str, Any]] = {}
    for r in status_rows:
        p = _parse_status(r)
        if p is None:
            discarded += 1
        else:
            statuses[p["station_id"]] = p

    stations: list[Station] = []
    for r in info_rows:
        p = _parse_info(r)
        if p is None:
            discarded += 1
            continue
        st = statuses.get(p["station_id"])
        if st is None:
            continue  # 状況がわからないポートは使わない
        s = Station(**p, **{k: v for k, v in st.items() if k != "station_id"})
        if is_osaka_station(s):
            stations.append(s)

    if not stations:
        raise GbfsError("大阪エリアのポートが 1 件もありません")
    return Snapshot(tuple(stations), last_updated, min(info_ttl, status_ttl), discarded)


# --- キャッシュ付きクライアント -----------------------------------------------------
class GbfsClient:
    """取得結果をフィードの ttl の間だけメモリに保持する。

    Lambda では実行環境（コンテナ）が再利用される間だけキャッシュが効く。
    取得に失敗したときは、期限切れのキャッシュを返さずに GbfsError を送出する。
    """

    def __init__(self, base_url: str | None = None,
                 fetch: Callable[[str], Any] = fetch_json,
                 clock: Callable[[], float] = time.time) -> None:
        base = base_url or os.environ.get("GBFS_BASE_URL") or DEFAULT_BASE_URL
        if not base.startswith("https://"):
            # file:// などのスキームを urlopen に渡さない
            raise ValueError("GBFS_BASE_URL は https:// で始まる必要があります")
        self.base_url = base.rstrip("/")
        self._fetch = fetch
        self._clock = clock
        self._cached: Snapshot | None = None
        self._fetched_at = 0.0
        self._lock = threading.Lock()

    def get_snapshot(self) -> Snapshot:
        # ロックを持ったまま取得する。同時に来たリクエストが重複して取得する（stampede）のを防ぐ。
        # 取得が遅いと後続が待たされるが、Lambda は 1 つの実行環境で
        # 1 リクエストずつ処理するので影響は小さい。
        with self._lock:
            now = self._clock()
            if (self._cached is not None and now - self._fetched_at < self._cached.ttl
                    and now - self._cached.last_updated <= MAX_DATA_AGE_SECONDS):
                return self._cached
            self._cached = None  # 期限切れのキャッシュは失敗時にも使わない
            info = self._fetch(f"{self.base_url}/station_information.json")
            status = self._fetch(f"{self.base_url}/station_status.json")
            snapshot = parse_snapshot(info, status, now)
            self._cached, self._fetched_at = snapshot, now
            return snapshot
