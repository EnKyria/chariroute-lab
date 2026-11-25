// 画面で選んだ地点（出発地・目的地）の表現と、API の Location への変換。
// 座標はメモリ（React の状態）にだけ置き、localStorage などには保存しない。
import type { Location } from './api/types'

export type PointSource = 'preset' | 'gps' | 'place' | 'map'

export interface SelectedPoint {
  source: PointSource
  name: string
  lat: number
  lon: number
  presetId?: string
}

/** バックエンドの OSAKA_BBOX（app/gbfs.py）と同じ範囲。外の地点は送らずに画面で知らせる。 */
export const OSAKA_BBOX = { latMin: 34.55, latMax: 34.78, lonMin: 135.35, lonMax: 135.65 }
export const OSAKA_CENTER: [number, number] = [34.6863, 135.52]

export function inOsaka(lat: number, lon: number): boolean {
  return (
    lat >= OSAKA_BBOX.latMin &&
    lat <= OSAKA_BBOX.latMax &&
    lon >= OSAKA_BBOX.lonMin &&
    lon <= OSAKA_BBOX.lonMax
  )
}

export function toLocation(p: SelectedPoint): Location {
  if (p.source === 'preset' && p.presetId) return { preset_id: p.presetId }
  if (p.source === 'place') return { lat: p.lat, lon: p.lon, source: 'place', name: p.name }
  return { lat: p.lat, lon: p.lon, source: p.source === 'preset' ? 'map' : p.source }
}

export const SOURCE_LABEL: Record<PointSource, string> = {
  preset: 'プリセット',
  gps: '現在地',
  place: '地点検索',
  map: '地図',
}

/** 2 点が実質的に同じ地点か（約 10 m 未満。バックエンドの判定と同じ基準）。 */
export function samePoint(a: SelectedPoint, b: SelectedPoint): boolean {
  if (a.presetId && a.presetId === b.presetId) return true
  const dLat = (a.lat - b.lat) * 111_195
  const dLon = (a.lon - b.lon) * 111_195 * Math.cos((a.lat * Math.PI) / 180)
  return Math.hypot(dLat, dLon) < 10
}
