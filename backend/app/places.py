"""地点検索（Nominatim）。plan §6.8。

- 呼ぶのは、ユーザーが検索ボタンを押したときだけ（API の呼び出し 1 回につき、最大 1 回の送信）。
- リミッターは OSRM と別に 1 つ（プロセス全体で共有）。自動リトライはしない。
- キャッシュ：プロセス内、24 時間・最大 200 件。キーは正規化した検索語。
  入れるのは 1 件以上の結果（OSM の公開されている地物の名称・表示名・座標）だけ。
  0 件と失敗は入れない。
- 検索語とキャッシュの内容はログに出さない。例外のメッセージにも入れない。
"""

import math
import os
import threading
import time
import unicodedata
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.gbfs import OSAKA_BBOX
from app.outbound import (
    DEFAULT_NOMINATIM_URL,
    REQUEST_TIMEOUT_SECONDS,
    Fetcher,
    OutboundError,
    RateLimiter,
    external_apis_enabled,
    http_get_json,
    https_url,
    outbound_headers,
    query,
)

MIN_QUERY_LEN = 2
MAX_QUERY_LEN = 64
RESULT_LIMIT = 5
CACHE_TTL_SECONDS = 24 * 3600
CACHE_MAX_ENTRIES = 200


class PlacesError(Exception):
    """Nominatim の失敗（503 にする）。disabled は、設定で外部への送信を止めているとき True。"""

    def __init__(self, message: str, *, busy: bool = False, disabled: bool = False) -> None:
        super().__init__(message)
        self.busy = busy
        self.disabled = disabled


@dataclass(frozen=True)
class Place:
    name: str
    label: str
    lat: float
    lon: float


def normalize_query(q: str) -> str:
    """全角・半角、大文字・小文字、連続する空白の違いをそろえる。"""
    return " ".join(unicodedata.normalize("NFKC", q).casefold().split())


def _in_osaka(lat: float, lon: float) -> bool:
    lat_min, lat_max, lon_min, lon_max = OSAKA_BBOX
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def _parse(body: Any) -> list[Place]:
    if not isinstance(body, list):
        raise PlacesError("Nominatim の応答が配列ではありません")
    places = []
    for r in body:
        if not isinstance(r, dict):
            continue
        try:
            lat, lon = float(r["lat"]), float(r["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (math.isfinite(lat) and math.isfinite(lon) and _in_osaka(lat, lon)):
            continue
        label = r.get("display_name") if isinstance(r.get("display_name"), str) else ""
        name = r.get("name") if isinstance(r.get("name"), str) and r.get("name") else (
            label.split(",")[0].strip())
        if not name:
            continue
        places.append(Place(name[:100], label[:300], round(lat, 6), round(lon, 6)))
    return places


class PlacesClient:
    def __init__(self, base_url: str | None = None, limiter: RateLimiter | None = None,
                 fetch: Fetcher = http_get_json, clock: Callable[[], float] = time.monotonic,
                 timeout: float = REQUEST_TIMEOUT_SECONDS,
                 enabled: Callable[[], bool] = external_apis_enabled) -> None:
        self.base_url = https_url(base_url or os.environ.get("NOMINATIM_URL"),
                                  DEFAULT_NOMINATIM_URL, "NOMINATIM_URL")
        self.limiter = limiter or RateLimiter()
        self._fetch = fetch
        self._clock = clock
        self.timeout = timeout
        self._enabled = enabled  # 送信のたびに確かめる（既定は環境変数。plan §7.3）
        self._cache: OrderedDict[str, tuple[float, list[Place]]] = OrderedDict()
        self._cache_lock = threading.Lock()

    def _cached(self, key: str) -> list[Place] | None:
        with self._cache_lock:
            hit = self._cache.get(key)
            if hit is None:
                return None
            if self._clock() - hit[0] >= CACHE_TTL_SECONDS:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return hit[1]

    def _store(self, key: str, places: list[Place]) -> None:
        with self._cache_lock:
            self._cache[key] = (self._clock(), places)
            self._cache.move_to_end(key)
            while len(self._cache) > CACHE_MAX_ENTRIES:
                self._cache.popitem(last=False)

    def search(self, q: str) -> list[Place]:
        """q は呼び出し側で 2〜64 文字に検証済みとする。

        無効のときは、キャッシュも使わずに PlacesError(disabled=True) にする。
        """
        if not self._enabled():
            raise PlacesError("外部 API への送信は設定で無効です", disabled=True)
        key = normalize_query(q)
        cached = self._cached(key)
        if cached is not None:
            return cached
        lat_min, lat_max, lon_min, lon_max = OSAKA_BBOX
        url = f"{self.base_url}/search?" + query({
            "q": q.strip(), "format": "jsonv2", "limit": str(RESULT_LIMIT),
            "countrycodes": "jp", "viewbox": f"{lon_min},{lat_max},{lon_max},{lat_min}",
            "bounded": "1", "accept-language": "ja",
        })
        headers = outbound_headers()
        try:
            res = self.limiter.run(lambda: self._fetch(url, self.timeout, headers))
        except OutboundError as e:
            raise PlacesError(f"Nominatim: {e}", busy=e.busy) from e
        if res.status == 429:
            raise PlacesError("Nominatim: 混雑（HTTP 429）", busy=True)
        if res.status != 200:
            raise PlacesError(f"Nominatim: HTTP {res.status}")
        places = _parse(res.body)
        if places:
            self._store(key, places)
        return places
