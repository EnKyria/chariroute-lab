// 検索結果から地図に描く点と線を作る（純粋関数。Leaflet に依存しないのでテストしやすい）。
import type { RouteResponse } from './api/types'

export type MapPointKind = 'origin' | 'rent' | 'return' | 'destination'

export interface MapPoint {
  kind: MapPointKind
  label: string
  name: string
  lat: number
  lon: number
}

export interface MapSegment {
  mode: 'walk' | 'bike'
  from: [number, number]
  to: [number, number]
}

export interface MapModel {
  points: MapPoint[]
  segments: MapSegment[]
}

const LABEL: Record<MapPointKind, string> = {
  origin: '出発地',
  rent: '貸出ポート',
  return: '返却ポート',
  destination: '目的地',
}

/**
 * シェアサイクルの経路があれば 出発地 → 貸出 → 返却 → 目的地、
 * なければ 出発地 → 目的地（徒歩）を、それぞれ直線で結ぶ。
 */
export function buildMapModel(result: RouteResponse): MapModel {
  const { origin, destination, bike_share: bike } = result
  const stops: { kind: MapPointKind; name: string; lat: number; lon: number }[] = bike
    ? [
        { kind: 'origin', ...origin },
        { kind: 'rent', ...bike.rent_station },
        { kind: 'return', ...bike.return_station },
        { kind: 'destination', ...destination },
      ]
    : [
        { kind: 'origin', ...origin },
        { kind: 'destination', ...destination },
      ]

  const points: MapPoint[] = stops.map((s) => ({
    kind: s.kind,
    label: LABEL[s.kind],
    name: s.name,
    lat: s.lat,
    lon: s.lon,
  }))

  const segments: MapSegment[] = []
  for (let i = 0; i + 1 < points.length; i++) {
    const a = points[i]
    const b = points[i + 1]
    if (!a || !b) continue
    segments.push({
      // 貸出ポート → 返却ポートの区間だけが自転車
      mode: a.kind === 'rent' ? 'bike' : 'walk',
      from: [a.lat, a.lon],
      to: [b.lat, b.lon],
    })
  }
  return { points, segments }
}
