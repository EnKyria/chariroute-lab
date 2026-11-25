// 地図（Leaflet / React Leaflet + OpenStreetMap タイル）。
// - 経路は OSRM の Route の形状（道路に沿った経路）を実線で描く。
// - pickTarget が指定されている間は、地図のタップでその地点（出発地か目的地）を設定する。
import 'leaflet/dist/leaflet.css'
import { useEffect } from 'react'
import {
  CircleMarker,
  MapContainer,
  Polyline,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from 'react-leaflet'
import type { BikeShareRoute } from './api/types'
import { buildMapModel, POINT_LABEL, type MapPointKind } from './mapPoints'
import { OSAKA_CENTER, type SelectedPoint } from './points'

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

export type PickTarget = 'origin' | 'destination'

interface Props {
  origin: SelectedPoint | null
  destination: SelectedPoint | null
  bike: BikeShareRoute | null
  pickTarget: PickTarget | null
  onPick: (target: PickTarget, lat: number, lon: number) => void
}

function ClickToPick({ target, onPick }: { target: PickTarget | null; onPick: Props['onPick'] }) {
  useMapEvents({
    click(e) {
      if (target) onPick(target, e.latlng.lat, e.latlng.lng)
    },
  })
  return null
}

function FitBounds({ bounds }: { bounds: [number, number][] }) {
  const map = useMap()
  const key = bounds.flat().join(',')
  useEffect(() => {
    if (bounds.length >= 2) map.fitBounds(bounds, { padding: [32, 32], maxZoom: 17 })
    else if (bounds.length === 1 && bounds[0]) map.setView(bounds[0], 15)
    // key が変わったときだけ合わせ直す（タップのたびに地図が動かないよう、配列そのものは見ない）
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, map])
  return null
}

export default function RouteMap({ origin, destination, bike, pickTarget, onPick }: Props) {
  const { points, lines, bounds } = buildMapModel(origin, destination, bike)

  return (
    <figure className="map">
      <MapContainer
        center={OSAKA_CENTER}
        zoom={12}
        scrollWheelZoom={false}
        className={`map-canvas${pickTarget ? ' picking' : ''}`}
      >
        <TileLayer url={TILE_URL} attribution={TILE_ATTRIBUTION} maxZoom={19} />
        <ClickToPick target={pickTarget} onPick={onPick} />
        <FitBounds bounds={bounds} />
        {lines.map((l, i) => (
          <Polyline
            key={i}
            positions={l.positions}
            pathOptions={{
              color: l.mode === 'bike' ? '#15803d' : '#475569',
              weight: l.mode === 'bike' ? 6 : 4,
              opacity: 0.9,
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
        {pickTarget && (
          <p className="pick-hint" role="status">
            地図をタップして{POINT_LABEL[pickTarget]}を指定してください
          </p>
        )}
        <ul className="legend">
          {(Object.keys(COLOR) as MapPointKind[]).map((k) => (
            <li key={k}>
              <span className="dot" style={{ background: COLOR[k] }} aria-hidden="true" />
              {POINT_LABEL[k]}
            </li>
          ))}
          <li>
            <span className="line line-walk" aria-hidden="true" />
            徒歩
          </li>
          <li>
            <span className="line line-bike" aria-hidden="true" />
            自転車
          </li>
        </ul>
        {bike && (
          <p className="note">線は OSRM で取得した道路に沿った経路です（OpenStreetMap のデータにもとづく）。</p>
        )}
      </figcaption>
    </figure>
  )
}
