// 地図に描く点と線を作る（純粋関数。Leaflet に依存しないのでテストしやすい）。
// PHASE 4.5：線は OSRM の Route の形状（道路に沿った経路）。直線の概算は描かない。
import type { BikeShareRoute } from './api/types'
import type { SelectedPoint } from './points'

export type MapPointKind = 'origin' | 'rent' | 'return' | 'destination'

export interface MapPoint {
  kind: MapPointKind
  label: string
  name: string
  lat: number
  lon: number
}

export interface MapLine {
  mode: 'walk' | 'bike'
  positions: [number, number][]
}

export interface MapModel {
  points: MapPoint[]
  lines: MapLine[]
  /** 表示範囲に含める座標（点と線のすべて） */
  bounds: [number, number][]
}

export const POINT_LABEL: Record<MapPointKind, string> = {
  origin: '出発地',
  rent: '貸出ポート',
  return: '返却ポート',
  destination: '目的地',
}

export function buildMapModel(
  origin: SelectedPoint | null,
  destination: SelectedPoint | null,
  bike: BikeShareRoute | null,
): MapModel {
  const stops: { kind: MapPointKind; name: string; lat: number; lon: number }[] = []
  if (origin) stops.push({ kind: 'origin', ...origin })
  if (bike) {
    stops.push({ kind: 'rent', ...bike.rent_station })
    stops.push({ kind: 'return', ...bike.return_station })
  }
  if (destination) stops.push({ kind: 'destination', ...destination })

  const points: MapPoint[] = stops.map((s) => ({
    kind: s.kind,
    label: POINT_LABEL[s.kind],
    name: s.name,
    lat: s.lat,
    lon: s.lon,
  }))
  const lines: MapLine[] = (bike?.legs ?? [])
    .filter((leg) => leg.geometry.length >= 2)
    .map((leg) => ({ mode: leg.mode, positions: leg.geometry }))
  const bounds: [number, number][] = [
    ...points.map((p) => [p.lat, p.lon] as [number, number]),
    ...lines.flatMap((l) => l.positions),
  ]
  return { points, lines, bounds }
}
