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

export interface MarkerStyle {
  fill: string
  stroke: string
  weight: number
  radius: number
}

// 点の配色：出発地＝青、貸出＝緑、返却＝オレンジ、目的地＝赤（線は徒歩＝グレー、自転車＝緑）。
// 返却（オレンジ）と目的地（赤）は色相が近いので、明度も大きく変える（明るいオレンジ / 濃い赤）。
// 返却ポートには濃い茶色の太めの枠線を付け、地図のタイルや自転車の線からも浮かせる。
export const MARKER_STYLE: Record<MapPointKind, MarkerStyle> = {
  origin: { fill: '#1d4ed8', stroke: '#ffffff', weight: 2, radius: 11 },
  rent: { fill: '#15803d', stroke: '#ffffff', weight: 2, radius: 8 },
  return: { fill: '#fb923c', stroke: '#7c2d12', weight: 3, radius: 8 },
  destination: { fill: '#b91c1c', stroke: '#ffffff', weight: 2, radius: 11 },
}

export const LINE_STYLE: Record<MapLine['mode'], { color: string; weight: number }> = {
  walk: { color: '#475569', weight: 4 },
  bike: { color: '#15803d', weight: 6 },
}

export const LEGEND_ORDER: MapPointKind[] = ['origin', 'rent', 'return', 'destination']

// 描く順（後のものが上に重なる）。出発地・目的地を大きめの円で先に描き、ポートを上に重ねる。
// 目的地のすぐ近くに返却ポートがあっても、「赤い輪の中のオレンジの点」として両方が見える。
const DRAW_ORDER: Record<MapPointKind, number> = { origin: 0, destination: 1, rent: 2, return: 3 }

export function sortForDrawing(points: MapPoint[]): MapPoint[] {
  return [...points].sort((a, b) => DRAW_ORDER[a.kind] - DRAW_ORDER[b.kind])
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
