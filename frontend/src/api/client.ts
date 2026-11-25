// API クライアント。HTTP の詳細（URL、ステータスコード、エラー本文）はここで吸収し、
// UI には「成功した型付きの値」か「種類つきの ApiError」だけを渡す。
import type { PresetsResponse, RouteRequest, RouteResponse } from './types'

/** 空なら同一オリジン（本番は CloudFront、ローカルは Vite の proxy）。 */
const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? ''

export type ApiErrorKind =
  | 'input' // 400（不明な地点・同じ地点）、422（形式エラー）
  | 'gbfs_unavailable' // 503（GBFS の取得失敗）
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

/** FastAPI の HTTPException は detail が文字列。422 は配列なので使わない。 */
function detailOf(body: unknown): string | null {
  return isObject(body) && typeof body.detail === 'string' ? body.detail : null
}

async function readJson(res: Response): Promise<unknown> {
  try {
    return await res.json()
  } catch {
    return null
  }
}

function toHttpError(status: number, body: unknown): ApiError {
  const detail = detailOf(body)
  switch (status) {
    case 400:
      return new ApiError('input', detail ?? '入力内容を確認してください', status)
    case 422:
      return new ApiError('input', '入力内容の形式が正しくありません', status)
    case 503:
      return new ApiError(
        'gbfs_unavailable',
        detail ?? 'ポート情報を取得できませんでした。しばらくしてから再度お試しください',
        status,
      )
    default:
      return new ApiError('server', `サーバーでエラーが発生しました（HTTP ${status}）`, status)
  }
}

async function request(path: string, init?: RequestInit): Promise<unknown> {
  let res: Response
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...init?.headers },
    })
  } catch {
    throw new ApiError('network', 'サーバーに接続できませんでした。通信環境を確認してください')
  }
  const body = await readJson(res)
  if (!res.ok) throw toHttpError(res.status, body)
  return body
}

// 型の宣言だけでは実行時の値を保証できないため、UI が依存する部分を確かめる。
function isPresetsResponse(v: unknown): v is PresetsResponse {
  return isObject(v) && Array.isArray(v.presets)
}

function hasNumbers(v: unknown, keys: readonly string[]): boolean {
  return isObject(v) && keys.every((k) => typeof v[k] === 'number')
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

const BIKE_NUMBERS = [
  'walk_to_rent_m',
  'bike_m',
  'walk_from_return_m',
  'walk_to_rent_minutes',
  'rent_minutes',
  'bike_minutes',
  'return_minutes',
  'walk_from_return_minutes',
  'total_minutes',
] as const

function isBikeShareRoute(v: unknown): boolean {
  return (
    isObject(v) &&
    isStation(v.rent_station) &&
    isStation(v.return_station) &&
    hasNumbers(v, BIKE_NUMBERS)
  )
}

// UI が表示に使う項目の型まで確かめる。欠けていれば画面を壊さずにエラーとして扱う。
function isRouteResponse(v: unknown): v is RouteResponse {
  return (
    isObject(v) &&
    (v.recommended === 'bike_share' || v.recommended === 'walk') &&
    isPlace(v.origin) &&
    isPlace(v.destination) &&
    hasNumbers(v.walk, ['distance_m', 'total_minutes']) &&
    hasStrings(v.data, ['last_updated', 'attribution', 'license', 'license_url', 'dataset_url']) &&
    (v.bike_share === null || isBikeShareRoute(v.bike_share))
  )
}

const INVALID = 'サーバーから想定外の応答がありました'

export async function fetchPresets(): Promise<PresetsResponse> {
  const body = await request('/api/presets')
  if (!isPresetsResponse(body)) throw new ApiError('invalid_response', INVALID)
  return body
}

export async function searchRoute(req: RouteRequest): Promise<RouteResponse> {
  const body = await request('/api/routes/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!isRouteResponse(body)) throw new ApiError('invalid_response', INVALID)
  return body
}
