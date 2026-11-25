// バックエンド（backend/main.py の Pydantic モデル / OpenAPI スキーマ）と同じ構造・フィールド名の型。
// フィールドを変えるときは backend 側と同時に変える。
// PHASE 4.5：地点は Location（プリセットか座標）、経路は道路に沿った 3 区間（legs）。
// 徒歩のみの経路（walk）とおすすめ（recommended）は廃止した（docs/plan.md §6.3）。

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

export type CoordSource = 'gps' | 'place' | 'map'

/** Location：{preset_id} か {lat, lon, source}（place のときは name も送れる） */
export type Location =
  | { preset_id: string }
  | { lat: number; lon: number; source: CoordSource; name?: string }

/** RouteRequest（POST /api/routes/search の本文） */
export interface RouteRequest {
  origin: Location
  destination: Location
}

/** PlaceOut（応答の出発地・目的地） */
export interface PlaceOut {
  name: string
  lat: number
  lon: number
  source: 'preset' | CoordSource
  preset_id?: string | null
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

/** LegOut。distance_m は道路距離、minutes は推定所要時間（道路距離 ÷ 速度）。geometry は [lat, lon] の列。 */
export interface Leg {
  mode: 'walk' | 'bike'
  distance_m: number
  minutes: number
  geometry: [number, number][]
}

/** BikeShareRoute。legs は 徒歩（出発地 → 貸出）・自転車（貸出 → 返却）・徒歩（返却 → 目的地）の 3 区間。 */
export interface BikeShareRoute {
  rent_station: Station
  return_station: Station
  legs: Leg[]
  rent_minutes: number
  return_minutes: number
  total_minutes: number
}

export interface SearchStats {
  rent_candidates: number
  return_candidates: number
  pairs_evaluated: number
}

export interface RoutingSource {
  provider: string
  provider_url: string
  map_data: string
  map_data_url: string
  fixthemap_url: string
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
  routing: RoutingSource
}

/** RouteResponse（POST /api/routes/search） */
export interface RouteResponse {
  origin: PlaceOut
  destination: PlaceOut
  /** 利用できるシェアサイクルの経路がなければ null */
  bike_share: BikeShareRoute | null
  search: SearchStats
  data: DataSource
}

/** PlacesRequest（POST /api/places/search の本文）。q は 2〜64 文字。 */
export interface PlacesRequest {
  q: string
}

/** PlaceCandidate */
export interface PlaceCandidate {
  name: string
  label: string
  lat: number
  lon: number
}

/** PlacesResponse */
export interface PlacesResponse {
  places: PlaceCandidate[]
  attribution: string
}
