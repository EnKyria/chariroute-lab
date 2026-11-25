"""外部サービス（OSRM・Nominatim）の偽物。実ネットワークには接続しない。

応答の形式は OSRM の docs/http.md（Table・Route）と Nominatim の jsonv2 にもとづく。
"""

import urllib.parse
from collections.abc import Callable
from typing import Any

from app.osrm import OsrmClient
from app.outbound import HttpResult, OutboundError, RateLimiter
from app.routing import Point, haversine_m

FOOT_URL = "https://osrm.test/routed-foot"
BIKE_URL = "https://osrm.test/routed-bike"

DistanceFn = Callable[[str, Point, Point], float | None]


def detour_distance(_profile: str, a: Point, b: Point) -> float | None:
    """既定：直線距離 × 1.3（直線距離モデルと同じ値になる）。"""
    return haversine_m(a, b) * 1.3


class ManualClock:
    """time.monotonic と time.sleep の代わり。sleep は時計を進めるだけ。"""

    def __init__(self, now: float = 1000.0) -> None:
        self.now = now
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def parse_osrm_url(url: str) -> tuple[str, str, list[Point], dict[str, str]]:
    """(profile, service, points, params) を返す。"""
    parsed = urllib.parse.urlsplit(url)
    parts = parsed.path.strip("/").split("/")  # routed-foot/table/v1/driving/coords
    profile = "foot" if parts[0] == "routed-foot" else "bike"
    service = parts[1]
    assert parts[2:4] == ["v1", "driving"], url
    points = []
    for c in parts[4].split(";"):
        lon, lat = c.split(",")
        points.append(Point(float(lat), float(lon)))
    params = dict(urllib.parse.parse_qsl(parsed.query))
    return profile, service, points, params


class FakeOsrm:
    """OSRM の Fetcher の偽物。

    distance(profile, a, b) で道路距離を決める（None は到達できない）。
    """

    def __init__(self, distance: DistanceFn = detour_distance, snap_m: float = 5.0) -> None:
        self.distance = distance
        self.snap_m = snap_m
        self.route_distance: DistanceFn | None = None  # Route だけ別の距離にしたいとき
        self.calls: list[tuple[str, str, int]] = []  # (profile, service, 地点数)
        self.urls: list[str] = []
        self.headers: list[dict[str, str]] = []
        self.timeouts: list[float] = []
        # service → 返す応答（HttpResult）か送出する例外。設定すると正常の応答の代わりに使う
        self.override: dict[str, HttpResult | Exception] = {}
        # 地点のインデックスか座標 → スナップ距離
        self.snap_override: dict[int | Point, float] = {}

    def __call__(self, url: str, timeout: float, headers: dict[str, str]) -> HttpResult:
        profile, service, points, params = parse_osrm_url(url)
        self.calls.append((profile, service, len(points)))
        self.urls.append(url)
        self.headers.append(headers)
        self.timeouts.append(timeout)
        o = self.override.get(service)
        if isinstance(o, Exception):
            raise o
        if o is not None:
            return o
        if service == "table":
            return HttpResult(200, self._table(profile, points, params))
        return HttpResult(200, self._route(profile, points))

    def _wp(self, i: int, p: Point) -> dict[str, Any]:
        snap = self.snap_override.get(p, self.snap_override.get(i, self.snap_m))
        return {"distance": snap, "location": [p.lon, p.lat],
                "name": ""}

    def _table(self, profile: str, points: list[Point], params: dict[str, str]) -> Any:
        assert params["annotations"] == "distance"
        src = [int(x) for x in params["sources"].split(";")]
        dst = [int(x) for x in params["destinations"].split(";")]
        dist = [[self.distance(profile, points[i], points[j]) for j in dst] for i in src]
        return {"code": "Ok", "distances": dist,
                "sources": [self._wp(i, points[i]) for i in src],
                "destinations": [self._wp(j, points[j]) for j in dst]}

    def _route(self, profile: str, points: list[Point]) -> Any:
        a, b = points
        fn = self.route_distance or self.distance
        d = fn(profile, a, b)
        if d is None:
            return {"code": "NoRoute", "message": "Impossible route between points"}
        mid = [(a.lon + b.lon) / 2, (a.lat + b.lat) / 2]
        return {"code": "Ok", "routes": [{
            "distance": d, "duration": d / 2.0, "weight": d,
            "geometry": {"type": "LineString",
                         "coordinates": [[a.lon, a.lat], mid, [b.lon, b.lat]]},
            "legs": []}],
            "waypoints": [self._wp(0, a), self._wp(1, b)]}

    def services(self) -> list[tuple[str, str]]:
        return [(p, s) for p, s, _ in self.calls]


def osrm_client(fake: FakeOsrm, clock: ManualClock | None = None) -> OsrmClient:
    clock = clock or ManualClock()
    return OsrmClient(FOOT_URL, BIKE_URL, RateLimiter(clock=clock, sleep=clock.sleep), fake)


class FakeNominatim:
    def __init__(self, results: list[dict[str, Any]] | None = None) -> None:
        self.results = results if results is not None else [
            {"name": "大阪駅", "display_name": "大阪駅, 梅田3丁目, 北区, 大阪市, 日本",
             "lat": "34.7025", "lon": "135.4959", "category": "railway", "type": "station"},
        ]
        self.calls: list[str] = []
        self.headers: list[dict[str, str]] = []
        self.response: HttpResult | Exception | None = None

    def __call__(self, url: str, timeout: float, headers: dict[str, str]) -> HttpResult:
        self.calls.append(url)
        self.headers.append(headers)
        if isinstance(self.response, Exception):
            raise self.response
        if self.response is not None:
            return self.response
        return HttpResult(200, self.results)


def busy_error() -> HttpResult:
    return HttpResult(429, None)


def network_error() -> OutboundError:
    return OutboundError("通信エラー（TimeoutError）")
