// API クライアント。HTTP の詳細（URL、ステータスコード、エラー本文）はここで吸収し、
// UI には「成功した型付きの値」か「種類つきの ApiError」だけを渡す。
import type {
  PlacesRequest,
  PlacesResponse,
  PresetsResponse,
  RouteRequest,
  RouteResponse,
} from './types'

/** 空なら同一オリジン（本番は CloudFront、ローカルは Vite の proxy）。 */
const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? ''

export type ApiErrorKind =
  | 'input' // 400（不明な地点・同じ地点・エリア外・道路が近くにない）、422（形式エラー）
  | 'gbfs_unavailable' // 503（GBFS の取得失敗）
  | 'route_unavailable' // 503（OSRM の失敗・設定で停止中。道路の経路を取得できない）
  | 'places_unavailable' // 503（Nominatim の失敗・設定で停止中）
  | 'busy' // 503（外部サービスの混雑）、429（API の混雑）
  | 'server' // 上記以外の HTTP エラー
  | 'network' // 通信そのものの失敗
  | 'invalid_response' // 200 だが想定外の本文

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number | null

  constructor(kind: ApiErrorKind, message: string, status: number | null = null) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
  }
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null
}

/** 業務エラーは detail が文字列。422 は配列なので使わない。 */
function detailOf(body: unknown): string | null {
  return isObject(body) && typeof body.detail === 'string' ? body.detail : null
}

function codeOf(body: unknown): string | null {
  return isObject(body) && typeof body.code === 'string' ? body.code : null
}

async function readJson(res: Response): Promise<unknown> {
  try {
    return await res.json()
  } catch {
    return null
  }
}

const UNAVAILABLE: Record<string, { kind: ApiErrorKind; message: string }> = {
  gbfs_unavailable: {
    kind: 'gbfs_unavailable',
    message: 'ポート情報を取得できませんでした。しばらくしてから再度お試しください',
  },
  route_unavailable: {
    kind: 'route_unavailable',
    message: '道路の経路を取得できませんでした。しばらくしてから再度お試しください',
  },
  places_unavailable: {
    kind: 'places_unavailable',
    message: '地点を検索できませんでした。しばらくしてから再度お試しください',
  },
  // 外部 API への接続を設定で止めている環境（本番の既定。plan §7.3）。ダミーの結果は出さない
  route_disabled: {
    kind: 'route_unavailable',
    message: 'この環境では、道路の経路の検索（外部の経路サービスへの接続）を停止しています',
  },
  places_disabled: {
    kind: 'places_unavailable',
    message: 'この環境では、地点検索（外部の地点検索サービスへの接続）を停止しています',
  },
  route_busy: { kind: 'busy', message: '混雑しています。しばらくしてから再度お試しください' },
  places_busy: { kind: 'busy', message: '混雑しています。しばらくしてから再度お試しください' },
}

function toHttpError(status: number, body: unknown, fallback503: string): ApiError {
  const detail = detailOf(body)
  switch (status) {
    case 400:
      return new ApiError('input', detail ?? '入力内容を確認してください', status)
    case 422:
      return new ApiError('input', '入力内容の形式が正しくありません', status)
    case 429:
      return new ApiError('busy', '混雑しています。しばらくしてから再度お試しください', status)
    case 504:
      return new ApiError(
        'route_unavailable',
        '道路の経路を時間内に取得できませんでした。しばらくしてから再度お試しください',
        status,
      )
    case 503: {
      const known = UNAVAILABLE[codeOf(body) ?? fallback503] ?? UNAVAILABLE[fallback503]
      if (!known) return new ApiError('server', 'サービスを利用できません（HTTP 503）', status)
      return new ApiError(known.kind, detail ?? known.message, status)
    }
    default:
      return new ApiError('server', `サーバーでエラーが発生しました（HTTP ${status}）`, status)
  }
}

/** サーバーの検索の締め切り（25 秒）と API Gateway の上限（30 秒）より長くする。 */
export const REQUEST_TIMEOUT_MS = 35_000

async function request(path: string, init: RequestInit | undefined, fallback503: string) {
  let res: Response
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...init?.headers },
      signal: controller.signal,
    })
  } catch {
    throw new ApiError(
      'network',
      controller.signal.aborted
        ? '応答がありませんでした。しばらくしてから再度お試しください'
        : 'サーバーに接続できませんでした。通信環境を確認してください',
    )
  } finally {
    clearTimeout(timer)
  }
  const body = await readJson(res)
  if (!res.ok) throw toHttpError(res.status, body, fallback503)
  return body
}

// 型の宣言だけでは実行時の値を保証できないため、UI が依存する部分を確かめる。
function isPresetsResponse(v: unknown): v is PresetsResponse {
  return isObject(v) && Array.isArray(v.presets)
}

function hasNumbers(v: unknown, keys: readonly string[]): boolean {
  return isObject(v) && keys.every((k) => typeof v[k] === 'number' && Number.isFinite(v[k]))
}

function hasStrings(v: unknown, keys: readonly string[]): boolean {
  return isObject(v) && keys.every((k) => typeof v[k] === 'string')
}

function isPlace(v: unknown): boolean {
  return hasStrings(v, ['name']) && hasNumbers(v, ['lat', 'lon'])
}

function isStation(v: unknown): boolean {
  return isPlace(v) && hasNumbers(v, ['num_bikes_available', 'num_docks_available'])
}

function isLatLon(v: unknown): boolean {
  return (
    Array.isArray(v) &&
    v.length === 2 &&
    v.every((x) => typeof x === 'number' && Number.isFinite(x))
  )
}

function isLeg(v: unknown): boolean {
  return (
    isObject(v) &&
    (v.mode === 'walk' || v.mode === 'bike') &&
    hasNumbers(v, ['distance_m', 'minutes']) &&
    Array.isArray(v.geometry) &&
    v.geometry.every(isLatLon)
  )
}

function isBikeShareRoute(v: unknown): boolean {
  return (
    isObject(v) &&
    isStation(v.rent_station) &&
    isStation(v.return_station) &&
    Array.isArray(v.legs) &&
    v.legs.length === 3 &&
    v.legs.every(isLeg) &&
    hasNumbers(v, ['rent_minutes', 'return_minutes', 'total_minutes'])
  )
}

// UI が表示に使う項目の型まで確かめる。欠けていれば画面を壊さずにエラーとして扱う。
function isRouteResponse(v: unknown): v is RouteResponse {
  return (
    isObject(v) &&
    isPlace(v.origin) &&
    isPlace(v.destination) &&
    hasStrings(v.data, ['last_updated', 'attribution', 'license', 'license_url', 'dataset_url']) &&
    isObject(v.data) &&
    hasStrings(v.data.routing, ['provider', 'map_data', 'fixthemap_url']) &&
    (v.bike_share === null || isBikeShareRoute(v.bike_share))
  )
}

function isPlacesResponse(v: unknown): v is PlacesResponse {
  return (
    isObject(v) &&
    Array.isArray(v.places) &&
    v.places.every((p) => isPlace(p) && hasStrings(p, ['label']))
  )
}

const INVALID = 'サーバーから想定外の応答がありました'

export async function fetchPresets(): Promise<PresetsResponse> {
  const body = await request('/api/presets', undefined, 'gbfs_unavailable')
  if (!isPresetsResponse(body)) throw new ApiError('invalid_response', INVALID)
  return body
}

function postJson(body: unknown): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

export async function searchRoute(req: RouteRequest): Promise<RouteResponse> {
  const body = await request('/api/routes/search', postJson(req), 'route_unavailable')
  if (!isRouteResponse(body)) throw new ApiError('invalid_response', INVALID)
  return body
}

/** 地点検索。検索語を URL やアクセスログに残さないため POST で送る。 */
export async function searchPlaces(req: PlacesRequest): Promise<PlacesResponse> {
  const body = await request('/api/places/search', postJson(req), 'places_unavailable')
  if (!isPlacesResponse(body)) throw new ApiError('invalid_response', INVALID)
  return body
}
