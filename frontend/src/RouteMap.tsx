// 地図の表示（Leaflet / React Leaflet + OpenStreetMap タイル）。
// 線は道路に沿った経路ではなく、地点どうしを結んだ直線（破線）で、概算であることを凡例に明記する。
import 'leaflet/dist/leaflet.css'
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip } from 'react-leaflet'
import type { RouteResponse } from './api/types'
import { buildMapModel, type MapPointKind } from './mapPoints'

// OSM のタイル利用規約：HTTPS のこの URL を使い、地図上に帰属表示を出す。URL は差し替え可能にしておく。
const TILE_URL: string =
  import.meta.env.VITE_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors'

const COLOR: Record<MapPointKind, string> = {
  origin: '#1d4ed8',
  rent: '#15803d',
  return: '#c2410c',
  destination: '#b91c1c',
}

export default function RouteMap({ result }: { result: RouteResponse }) {
  const { points, segments } = buildMapModel(result)
  const bounds = points.map((p) => [p.lat, p.lon] as [number, number])
  // 結果が変わったら作り直して、表示範囲（bounds）を合わせ直す
  const key = bounds.flat().join(',')

  return (
    <figure className="map">
      <MapContainer
        key={key}
        bounds={bounds}
        boundsOptions={{ padding: [32, 32] }}
        scrollWheelZoom={false}
        className="map-canvas"
      >
        <TileLayer url={TILE_URL} attribution={TILE_ATTRIBUTION} maxZoom={19} />
        {segments.map((s, i) => (
          <Polyline
            key={i}
            positions={[s.from, s.to]}
            pathOptions={{
              color: s.mode === 'bike' ? '#15803d' : '#475569',
              weight: s.mode === 'bike' ? 5 : 3,
              dashArray: s.mode === 'bike' ? '10 8' : '4 6',
            }}
          />
        ))}
        {points.map((p) => (
          <CircleMarker
            key={p.kind}
            center={[p.lat, p.lon]}
            radius={9}
            pathOptions={{ color: '#fff', weight: 2, fillColor: COLOR[p.kind], fillOpacity: 1 }}
          >
            <Tooltip>
              {p.label}：{p.name}
            </Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>
      <figcaption>
        <ul className="legend">
          {points.map((p) => (
            <li key={p.kind}>
              <span className="dot" style={{ background: COLOR[p.kind] }} aria-hidden="true" />
              {p.label}
            </li>
          ))}
        </ul>
        <p className="note">
          破線は地点を直線で結んだ<strong>概算</strong>です。実際の道順ではありません。
        </p>
      </figcaption>
    </figure>
  )
}
