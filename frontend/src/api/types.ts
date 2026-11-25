// バックエンド（backend/main.py の Pydantic モデル / OpenAPI スキーマ）と同じ構造・フィールド名の型。
// フィールドを変えるときは backend 側と同時に変える。

/** PresetOut */
export interface Preset {
  id: string
  name: string
  lat: number
  lon: number
}

/** PresetsResponse（GET /api/presets） */
export interface PresetsResponse {
  presets: Preset[]
}

/** RouteRequest（POST /api/routes/search の本文）。各 id は 1〜64 文字。 */
export interface RouteRequest {
  origin_id: string
  destination_id: string
}

/** StationOut */
export interface Station {
  station_id: string
  name: string
  lat: number
  lon: number
  num_bikes_available: number
  num_docks_available: number
}

/** BikeShareRoute。距離（*_m）は迂回係数を掛ける前の直線距離、所要時間は概算（分）。 */
export interface BikeShareRoute {
  rent_station: Station
  return_station: Station
  walk_to_rent_m: number
  bike_m: number
  walk_from_return_m: number
  walk_to_rent_minutes: number
  rent_minutes: number
  bike_minutes: number
  return_minutes: number
  walk_from_return_minutes: number
  total_minutes: number
}

/** WalkOnlyRoute */
export interface WalkOnlyRoute {
  distance_m: number
  total_minutes: number
}

/**
 * DataSource。OpenAPI では last_updated 以外に既定値があり required ではないが、
 * サーバーは既定値も含めて常にシリアライズするため、ここでは必須として扱う。
 */
export interface DataSource {
  /** ISO 8601（JST のオフセット付き） */
  last_updated: string
  provider: string
  source: string
  license: string
  license_url: string
  attribution: string
  dataset_url: string
}

export type Recommended = 'bike_share' | 'walk'

/** RouteResponse（POST /api/routes/search） */
export interface RouteResponse {
  origin: Preset
  destination: Preset
  recommended: Recommended
  /** 利用可能な貸出・返却ポートの組がなければ null */
  bike_share: BikeShareRoute | null
  walk: WalkOnlyRoute
  data: DataSource
}
