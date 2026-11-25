"""FOSSGIS OSRM（routed-foot / routed-bike）のクライアント。

- 徒歩と自転車は別のホスト（プロファイルはサーバー側で固定）。リミッターは 1 つを共有する。
- 応答の形式は OSRM の docs/http.md にもとづく。
- 経路がない（NoRoute / NoTable / NoSegment）は OsrmNoRoute、それ以外の失敗は OsrmError（→ 503）。
- 例外のメッセージに URL や座標を入れない。
"""

import math
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from app.outbound import (
    DEFAULT_OSRM_BIKE_URL,
    DEFAULT_OSRM_FOOT_URL,
    REQUEST_TIMEOUT_SECONDS,
    TABLE_TIMEOUT_SECONDS,
    Fetcher,
    OutboundError,
    RateLimiter,
    external_apis_enabled,
    http_get_json,
    https_url,
    outbound_headers,
    query,
)
from app.routing import Point

Profile = Literal["foot", "bike"]
NO_ROUTE_CODES = frozenset({"NoRoute", "NoTable", "NoSegment"})


class OsrmError(Exception):
    """OSRM の失敗（503 にする）。disabled は、設定で外部への送信を止めているとき True。"""

    def __init__(self, message: str, *, busy: bool = False, disabled: bool = False) -> None:
        super().__init__(message)
        self.busy = busy
        self.disabled = disabled


class OsrmNoRoute(Exception):
    """道路でつながる経路がない（経路なしとして扱う）。"""


@dataclass(frozen=True)
class Table:
    distances: list[list[float | None]]  # [source][destination]（m）
    source_snap_m: list[float]  # 各 source の、入力の座標から道路までの距離
    destination_snap_m: list[float]


@dataclass(frozen=True)
class RouteShape:
    distance_m: float
    geometry: list[tuple[float, float]]  # [(lat, lon), ...]


def _coords(points: Sequence[Point]) -> str:
    return ";".join(f"{p.lon:.6f},{p.lat:.6f}" for p in points)


def _finite(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _snaps(waypoints: Any, n: int) -> list[float]:
    if not isinstance(waypoints, list) or len(waypoints) != n:
        raise OsrmError("Table の応答の地点数が一致しません")
    out = []
    for w in waypoints:
        d = w.get("distance") if isinstance(w, dict) else None
        if not _finite(d) or d < 0:
            raise OsrmError("Table の応答の地点が不正です")
        out.append(float(d))
    return out


class OsrmClient:
    def __init__(self, foot_url: str | None = None, bike_url: str | None = None,
                 limiter: RateLimiter | None = None, fetch: Fetcher = http_get_json,
                 timeout: float = REQUEST_TIMEOUT_SECONDS,
                 table_timeout: float = TABLE_TIMEOUT_SECONDS,
                 enabled: Callable[[], bool] = external_apis_enabled) -> None:
        self.urls: dict[Profile, str] = {
            "foot": https_url(foot_url or os.environ.get("OSRM_FOOT_URL"),
                              DEFAULT_OSRM_FOOT_URL, "OSRM_FOOT_URL"),
            "bike": https_url(bike_url or os.environ.get("OSRM_BIKE_URL"),
                              DEFAULT_OSRM_BIKE_URL, "OSRM_BIKE_URL"),
        }
        self.limiter = limiter or RateLimiter()
        self._fetch = fetch
        self.timeout = timeout  # Route
        self.table_timeout = table_timeout
        self._enabled = enabled  # 送信のたびに確かめる（既定は環境変数。plan §7.3）

    def clock(self) -> float:
        return self.limiter.clock()

    def _get(self, profile: Profile, service: str, points: Sequence[Point],
             params: dict[str, str], deadline: float | None) -> dict[str, Any]:
        if not self._enabled():
            # リミッターより前で止める（待たない・送らない・送信回数に数えない）
            raise OsrmError("外部 API への送信は設定で無効です", disabled=True)
        url = (f"{self.urls[profile]}/{service}/v1/driving/{_coords(points)}"
               f"?{query(params)}")
        headers = outbound_headers()
        limit = self.table_timeout if service == "table" else self.timeout

        def send() -> Any:
            remaining = limit if deadline is None else deadline - self.clock()
            return self._fetch(url, max(0.1, min(limit, remaining)), headers)

        try:
            res = self.limiter.run(send, deadline)
        except OutboundError as e:
            raise OsrmError(f"OSRM {service}（{profile}）: {e}", busy=e.busy) from e
        body = res.body
        code = body.get("code") if isinstance(body, dict) else None
        if code in NO_ROUTE_CODES:
            raise OsrmNoRoute(code)
        if res.status == 429:
            raise OsrmError(f"OSRM {service}（{profile}）: 混雑（HTTP 429）", busy=True)
        if res.status != 200 or code != "Ok" or not isinstance(body, dict):
            raise OsrmError(f"OSRM {service}（{profile}）: HTTP {res.status} code={code}")
        return body

    def table(self, profile: Profile, points: Sequence[Point], sources: Sequence[int],
              destinations: Sequence[int], deadline: float | None = None) -> Table:
        body = self._get(profile, "table", points, {
            "sources": ";".join(map(str, sources)),
            "destinations": ";".join(map(str, destinations)),
            "annotations": "distance",
        }, deadline)
        rows = body.get("distances")
        if not isinstance(rows, list) or len(rows) != len(sources):
            raise OsrmError("Table の応答に distances がありません")
        distances: list[list[float | None]] = []
        for row in rows:
            if not isinstance(row, list) or len(row) != len(destinations):
                raise OsrmError("Table の応答の行の長さが一致しません")
            cells: list[float | None] = []
            for v in row:
                if v is None:
                    cells.append(None)
                elif _finite(v) and v >= 0:
                    cells.append(float(v))
                else:
                    raise OsrmError("Table の応答の距離が不正です")
            distances.append(cells)
        return Table(distances, _snaps(body.get("sources"), len(sources)),
                     _snaps(body.get("destinations"), len(destinations)))

    def route(self, profile: Profile, a: Point, b: Point,
              deadline: float | None = None) -> RouteShape:
        body = self._get(profile, "route", [a, b], {
            "overview": "full", "geometries": "geojson", "steps": "false",
        }, deadline)
        routes = body.get("routes")
        r = routes[0] if isinstance(routes, list) and routes else None
        if not isinstance(r, dict) or not _finite(r.get("distance")) or r["distance"] < 0:
            raise OsrmError("Route の応答に routes がありません")
        geom = r.get("geometry")
        coords = geom.get("coordinates") if isinstance(geom, dict) else None
        if not isinstance(coords, list) or not coords:
            raise OsrmError("Route の応答に geometry がありません")
        shape: list[tuple[float, float]] = []
        for c in coords:
            if not (isinstance(c, list) and len(c) >= 2 and _finite(c[0]) and _finite(c[1])):
                raise OsrmError("Route の応答の座標が不正です")
            shape.append((round(float(c[1]), 6), round(float(c[0]), 6)))  # [lon,lat] → (lat,lon)
        return RouteShape(float(r["distance"]), shape)

