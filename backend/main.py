"""FastAPI アプリと Lambda ハンドラの定義。ロジックは app/ 配下にある。"""

import logging
import time
from datetime import UTC, datetime, timedelta, timezone
from functools import lru_cache
from typing import Annotated, Literal, Self

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from mangum import Mangum
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.gbfs import OSAKA_BBOX, GbfsClient, GbfsError
from app.osrm import OsrmClient, OsrmError
from app.places import MAX_QUERY_LEN, MIN_QUERY_LEN, PlacesClient, PlacesError
from app.presets import PRESETS, Preset, find_preset
from app.road_routing import Leg, NoNearbyRoad, search_road_route
from app.routing import Point, Station, haversine_m

logger = logging.getLogger("chariroute")
logger.setLevel(logging.INFO)

JST = timezone(timedelta(hours=9), "JST")
# 1 回の検索で OSRM に使える時間の合計。当初は 20 秒（plan §6.6）だったが、自転車の Table が
# 実測で約 9.7 秒かかったため 25 秒にした（engineering-notes §9.7）。
# API Gateway HTTP API の統合タイムアウトの上限（30 秒）より短くする。Lambda は 30 秒
SEARCH_DEADLINE_SECONDS = 25.0
SAME_LOCATION_M = 10.0  # 出発地と目的地がこれより近ければ「同じ地点」とみなす

app = FastAPI(title="chariroute-lab API")


# --- エラー ------------------------------------------------------------------------
class ApiFailure(Exception):
    """業務エラー（400）と外部サービスの失敗（503）。本文は {detail, code}。"""

    def __init__(self, status: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status, self.code, self.detail = status, code, detail


@app.exception_handler(ApiFailure)
def _api_failure(_: Request, exc: ApiFailure) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"detail": exc.detail, "code": exc.code})


@app.exception_handler(RequestValidationError)
def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    """422 の本文に入力値（座標・検索語）を含めない。NaN を含む入力でも 500 にしない。"""
    errors = [{"loc": [str(x) for x in e.get("loc", ())], "msg": str(e.get("msg", "")),
               "type": str(e.get("type", ""))} for e in exc.errors()]
    return JSONResponse(status_code=422, content={
        "detail": errors, "code": "invalid_request"})


GBFS_UNAVAILABLE = "ポート情報を取得できませんでした。しばらくしてから再度お試しください"
ROUTE_UNAVAILABLE = "道路の経路を取得できませんでした。しばらくしてから再度お試しください"
ROUTE_BUSY = "経路サービスが混雑しています。しばらくしてから再度お試しください"
PLACES_UNAVAILABLE = "地点を検索できませんでした。しばらくしてから再度お試しください"
PLACES_BUSY = "地点検索サービスが混雑しています。しばらくしてから再度お試しください"


# --- データの出典とライセンス -------------------------------------------------------
class RoutingSource(BaseModel):
    provider: str = "OSRM / FOSSGIS（routing.openstreetmap.de）"
    provider_url: str = "https://routing.openstreetmap.de/about.html"
    map_data: str = "© OpenStreetMap contributors（ODbL）"
    map_data_url: str = "https://www.openstreetmap.org/copyright"
    fixthemap_url: str = "https://www.openstreetmap.org/fixthemap"


class DataSource(BaseModel):
    last_updated: datetime  # GBFS フィードの last_updated（2 フィードのうち古いほう、JST）
    provider: str = "株式会社ドコモ・バイクシェア"
    source: str = "公共交通オープンデータ協議会（ODPT）"
    license: str = "CC BY 4.0"
    license_url: str = "https://creativecommons.org/licenses/by/4.0/deed.ja"
    # 提供者名の表記は ckan.odpt.org のデータセットページの「クレジット表示に関する情報」に合わせた
    attribution: str = (
        "出典：株式会社ドコモ・バイクシェア / 公共交通オープンデータ協議会"
        "（CC BY 4.0）のポート情報を加工して作成"
    )
    dataset_url: str = "https://ckan.odpt.org/dataset/c_bikeshare_gbfs-d-nationwide-bikeshare"
    routing: RoutingSource = RoutingSource()


# --- プリセット ---------------------------------------------------------------------
class PresetOut(BaseModel):
    id: str
    name: str
    lat: float
    lon: float


class PresetsResponse(BaseModel):
    presets: list[PresetOut]


# --- 経路検索 -----------------------------------------------------------------------
CoordSource = Literal["gps", "place", "map"]


class Location(BaseModel):
    """地点。{preset_id} か {lat, lon, source}（place のときは name も可）のどちらか。"""

    model_config = ConfigDict(extra="forbid")
    preset_id: str | None = Field(default=None, min_length=1, max_length=64)
    lat: float | None = Field(default=None, allow_inf_nan=False)
    lon: float | None = Field(default=None, allow_inf_nan=False)
    source: CoordSource | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def _one_form(self) -> Self:
        coords = (self.lat, self.lon, self.source)
        if self.preset_id is not None:
            if any(v is not None for v in (*coords, self.name)):
                raise ValueError("preset_id と座標は同時に指定できません")
        elif any(v is None for v in coords):
            raise ValueError("preset_id か、lat・lon・source を指定してください")
        elif self.name is not None and self.source != "place":
            raise ValueError("name は source が place のときだけ指定できます")
        return self


class RouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    origin: Location
    destination: Location


class PlaceOut(BaseModel):
    name: str
    lat: float
    lon: float
    source: Literal["preset", "gps", "place", "map"]
    preset_id: str | None = None


class StationOut(BaseModel):
    station_id: str
    name: str
    lat: float
    lon: float
    num_bikes_available: int
    num_docks_available: int


class LegOut(BaseModel):
    mode: Literal["walk", "bike"]
    distance_m: float  # 道路距離（OSRM の Route）
    minutes: float  # 推定所要時間 = 道路距離 ÷ ChariRoute の速度
    geometry: list[tuple[float, float]]  # [[lat, lon], ...]


class BikeShareRoute(BaseModel):
    rent_station: StationOut
    return_station: StationOut
    legs: list[LegOut]  # 徒歩（出発地 → 貸出）・自転車（貸出 → 返却）・徒歩（返却 → 目的地）
    rent_minutes: float
    return_minutes: float
    total_minutes: float


class SearchStats(BaseModel):
    rent_candidates: int
    return_candidates: int
    pairs_evaluated: int


class RouteResponse(BaseModel):
    origin: PlaceOut
    destination: PlaceOut
    bike_share: BikeShareRoute | None  # 利用できるシェアサイクルの経路がなければ null
    search: SearchStats
    data: DataSource


# --- 地点検索 -----------------------------------------------------------------------
class PlacesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str = Field(max_length=200)


class PlaceCandidate(BaseModel):
    name: str
    label: str
    lat: float
    lon: float


class PlacesResponse(BaseModel):
    places: list[PlaceCandidate]
    attribution: str = "地点検索：Nominatim / © OpenStreetMap contributors（ODbL）"


# --- 変換 --------------------------------------------------------------------------
def _preset_out(p: Preset) -> PresetOut:
    return PresetOut(id=p.id, name=p.name, lat=p.lat, lon=p.lon)


def _station_out(s: Station) -> StationOut:
    return StationOut(station_id=s.station_id, name=s.name, lat=s.lat, lon=s.lon,
                      num_bikes_available=s.num_bikes_available,
                      num_docks_available=s.num_docks_available)


def _leg_out(leg: Leg) -> LegOut:
    return LegOut(mode=leg.mode, distance_m=_r(leg.distance_m), minutes=_r(leg.minutes),
                  geometry=leg.geometry)


def _r(x: float) -> float:
    return round(x, 1)


_DEFAULT_NAMES = {"gps": "現在地", "map": "地図で選んだ地点", "place": "検索した地点"}


def _resolve(loc: Location) -> PlaceOut:
    if loc.preset_id is not None:
        p = find_preset(loc.preset_id)
        if p is None:
            raise ApiFailure(400, "unknown_preset", "指定された地点が見つかりません")
        return PlaceOut(name=p.name, lat=p.lat, lon=p.lon, source="preset", preset_id=p.id)
    assert loc.lat is not None and loc.lon is not None and loc.source is not None
    lat_min, lat_max, lon_min, lon_max = OSAKA_BBOX
    if not (lat_min <= loc.lat <= lat_max and lon_min <= loc.lon <= lon_max):
        raise ApiFailure(400, "outside_area", "大阪市の周辺の地点を指定してください")
    name = loc.name if loc.source == "place" and loc.name else _DEFAULT_NAMES[loc.source]
    return PlaceOut(name=name, lat=loc.lat, lon=loc.lon, source=loc.source)


@lru_cache(maxsize=1)
def get_gbfs_client() -> GbfsClient:
    """プロセス内で 1 つだけ作る（Lambda の実行環境が再利用される間はキャッシュが効く）。"""
    return GbfsClient()


@lru_cache(maxsize=1)
def get_osrm_client() -> OsrmClient:
    """OSRM のリミッターはプロセス全体で 1 つ（徒歩と自転車で共有）。"""
    return OsrmClient()


@lru_cache(maxsize=1)
def get_places_client() -> PlacesClient:
    """Nominatim のリミッターとキャッシュはプロセス全体で 1 つ。"""
    return PlacesClient()


# --- エンドポイント -----------------------------------------------------------------
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/presets", response_model=PresetsResponse)
def list_presets() -> PresetsResponse:
    return PresetsResponse(presets=[_preset_out(p) for p in PRESETS])


@app.post("/api/routes/search", response_model=RouteResponse)
def search_routes(request: RouteRequest,
                  gbfs: Annotated[GbfsClient, Depends(get_gbfs_client)],
                  osrm: Annotated[OsrmClient, Depends(get_osrm_client)]) -> RouteResponse:
    started = time.monotonic()
    deadline = osrm.clock() + SEARCH_DEADLINE_SECONDS
    origin, destination = _resolve(request.origin), _resolve(request.destination)
    if haversine_m(Point(origin.lat, origin.lon),
                   Point(destination.lat, destination.lon)) < SAME_LOCATION_M:
        raise ApiFailure(400, "same_location", "出発地と目的地が同じです")
    # ログに出すのは入力の種類・件数・結果の種類・処理時間だけ（座標や地点名は出さない）
    kinds = f"origin={origin.source} destination={destination.source}"

    try:
        snapshot = gbfs.get_snapshot()
    except GbfsError as e:
        logger.warning("GBFS の取得に失敗しました: %s", e)
        raise ApiFailure(503, "gbfs_unavailable", GBFS_UNAVAILABLE) from e

    try:
        result = search_road_route(Point(origin.lat, origin.lon),
                                   Point(destination.lat, destination.lon),
                                   snapshot.stations, osrm, deadline)
    except NoNearbyRoad as e:
        which = "出発地" if e.which == "origin" else "目的地"
        logger.info("route search %s result=no_road_nearby", kinds)
        raise ApiFailure(400, "no_road_nearby",
                         f"{which}の近くに道路が見つかりません。別の地点を指定してください") from e
    except OsrmError as e:
        logger.warning("route search %s result=osrm_error busy=%s: %s", kinds, e.busy, e)
        if e.busy:
            raise ApiFailure(503, "route_busy", ROUTE_BUSY) from e
        raise ApiFailure(503, "route_unavailable", ROUTE_UNAVAILABLE) from e

    logger.info("route search %s stations=%d rent=%d return=%d pairs=%d result=%s elapsed_ms=%d",
                kinds, len(snapshot.stations), result.rent_candidates, result.return_candidates,
                result.pairs_evaluated, "found" if result.route else "none",
                (time.monotonic() - started) * 1000)

    bike = None
    if result.route is not None:
        r = result.route
        bike = BikeShareRoute(
            rent_station=_station_out(r.rent_station),
            return_station=_station_out(r.return_station),
            legs=[_leg_out(leg) for leg in r.legs],
            rent_minutes=_r(r.rent_minutes), return_minutes=_r(r.return_minutes),
            total_minutes=_r(r.total_minutes),
        )
    return RouteResponse(
        origin=origin, destination=destination, bike_share=bike,
        search=SearchStats(rent_candidates=result.rent_candidates,
                           return_candidates=result.return_candidates,
                           pairs_evaluated=result.pairs_evaluated),
        data=DataSource(last_updated=datetime.fromtimestamp(snapshot.last_updated, UTC)
                        .astimezone(JST)),
    )


@app.post("/api/places/search", response_model=PlacesResponse)
def search_places(request: PlacesRequest,
                  places: Annotated[PlacesClient, Depends(get_places_client)]) -> PlacesResponse:
    q = request.q.strip()
    if not MIN_QUERY_LEN <= len(q) <= MAX_QUERY_LEN:
        raise ApiFailure(400, "invalid_query",
                         f"検索語は {MIN_QUERY_LEN}〜{MAX_QUERY_LEN} 文字で入力してください")
    try:
        found = places.search(q)
    except PlacesError as e:
        # 検索語はログに出さない（e のメッセージにも含まれない）
        logger.warning("place search result=error busy=%s: %s", e.busy, e)
        if e.busy:
            raise ApiFailure(503, "places_busy", PLACES_BUSY) from e
        raise ApiFailure(503, "places_unavailable", PLACES_UNAVAILABLE) from e
    logger.info("place search results=%d", len(found))
    return PlacesResponse(places=[PlaceCandidate(name=p.name, label=p.label, lat=p.lat,
                                                 lon=p.lon) for p in found])


handler = Mangum(app)
