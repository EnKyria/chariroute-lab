"""FastAPI アプリと Lambda ハンドラの定義。ロジックは app/ 配下にある。"""

import logging
from datetime import UTC, datetime, timedelta, timezone
from functools import lru_cache
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException
from mangum import Mangum
from pydantic import BaseModel, Field

from app.gbfs import GbfsClient, GbfsError
from app.presets import PRESETS, Preset, find_preset
from app.routing import Point, Station, search_route

logger = logging.getLogger("chariroute")
logger.setLevel(logging.INFO)

JST = timezone(timedelta(hours=9), "JST")

app = FastAPI(title="chariroute-lab API")


# --- データの出典とライセンス（CC BY 4.0 の表示義務） -----------------------------
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


# --- プリセット ---------------------------------------------------------------------
class PresetOut(BaseModel):
    id: str
    name: str
    lat: float
    lon: float


class PresetsResponse(BaseModel):
    presets: list[PresetOut]


# --- 経路検索 -----------------------------------------------------------------------
class RouteRequest(BaseModel):
    origin_id: str = Field(min_length=1, max_length=64)
    destination_id: str = Field(min_length=1, max_length=64)


class StationOut(BaseModel):
    station_id: str
    name: str
    lat: float
    lon: float
    num_bikes_available: int
    num_docks_available: int


class BikeShareRoute(BaseModel):
    rent_station: StationOut
    return_station: StationOut
    walk_to_rent_m: float
    bike_m: float  # 直線距離（迂回係数を掛ける前）
    walk_from_return_m: float
    walk_to_rent_minutes: float
    rent_minutes: float
    bike_minutes: float
    return_minutes: float
    walk_from_return_minutes: float
    total_minutes: float


class WalkOnlyRoute(BaseModel):
    distance_m: float  # 直線距離（迂回係数を掛ける前）
    total_minutes: float


class RouteResponse(BaseModel):
    origin: PresetOut
    destination: PresetOut
    recommended: Literal["bike_share", "walk"]
    bike_share: BikeShareRoute | None  # 利用可能なポートの組がなければ null
    walk: WalkOnlyRoute
    data: DataSource


def _preset_out(p: Preset) -> PresetOut:
    return PresetOut(id=p.id, name=p.name, lat=p.lat, lon=p.lon)


def _station_out(s: Station) -> StationOut:
    return StationOut(station_id=s.station_id, name=s.name, lat=s.lat, lon=s.lon,
                      num_bikes_available=s.num_bikes_available,
                      num_docks_available=s.num_docks_available)


def _r(x: float) -> float:
    return round(x, 1)


@lru_cache(maxsize=1)
def get_gbfs_client() -> GbfsClient:
    """プロセス内で 1 つだけ作る（Lambda の実行環境が再利用される間はキャッシュが効く）。"""
    return GbfsClient()


# --- エンドポイント -----------------------------------------------------------------
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/presets", response_model=PresetsResponse)
def list_presets() -> PresetsResponse:
    return PresetsResponse(presets=[_preset_out(p) for p in PRESETS])


@app.post("/api/routes/search", response_model=RouteResponse)
def search_routes(request: RouteRequest,
                  client: Annotated[GbfsClient, Depends(get_gbfs_client)]) -> RouteResponse:
    origin = find_preset(request.origin_id)
    destination = find_preset(request.destination_id)
    if origin is None or destination is None:
        raise HTTPException(status_code=400, detail="指定された地点が見つかりません")
    if origin.id == destination.id:
        raise HTTPException(status_code=400, detail="出発地と目的地が同じです")

    try:
        snapshot = client.get_snapshot()
    except GbfsError as e:
        logger.warning("GBFS の取得に失敗しました: %s", e)
        raise HTTPException(
            status_code=503,
            detail="ポート情報を取得できませんでした。しばらくしてから再度お試しください",
        ) from e

    result = search_route(Point(origin.lat, origin.lon), Point(destination.lat, destination.lon),
                          snapshot.stations)
    logger.info("route search %s->%s stations=%d pairs=%d recommended=%s",
                origin.id, destination.id, len(snapshot.stations), result.pairs_evaluated,
                result.recommended)

    bike = None
    if result.bike is not None:
        b = result.bike
        bike = BikeShareRoute(
            rent_station=_station_out(b.rent_station),
            return_station=_station_out(b.return_station),
            walk_to_rent_m=_r(b.walk_to_rent_m), bike_m=_r(b.bike_m),
            walk_from_return_m=_r(b.walk_from_return_m),
            walk_to_rent_minutes=_r(b.walk_to_rent_minutes), rent_minutes=_r(b.rent_minutes),
            bike_minutes=_r(b.bike_minutes), return_minutes=_r(b.return_minutes),
            walk_from_return_minutes=_r(b.walk_from_return_minutes),
            total_minutes=_r(b.total_minutes),
        )
    return RouteResponse(
        origin=_preset_out(origin),
        destination=_preset_out(destination),
        recommended=result.recommended,
        bike_share=bike,
        walk=WalkOnlyRoute(distance_m=_r(result.walk.distance_m),
                           total_minutes=_r(result.walk.total_minutes)),
        data=DataSource(last_updated=datetime.fromtimestamp(snapshot.last_updated, UTC)
                        .astimezone(JST)),
    )


handler = Mangum(app)
