import { describe, expect, it } from 'vitest'
import { buildMapModel, LEGEND_ORDER, LINE_STYLE, MARKER_STYLE, sortForDrawing } from './mapPoints'
import type { SelectedPoint } from './points'
import { bikeRoute } from './test/fixtures'

const origin: SelectedPoint = { source: 'preset', presetId: 'umeda', name: '梅田（JR大阪駅）', lat: 34.7025, lon: 135.4959 }
const destination: SelectedPoint = { source: 'map', name: '地図で選んだ地点', lat: 34.6666, lon: 135.5008 }

describe('buildMapModel', () => {
  it('シェアサイクルの経路：4 地点と、道路に沿った 3 本の線（徒歩・自転車・徒歩）', () => {
    const { points, lines, bounds } = buildMapModel(origin, destination, bikeRoute.bike_share)
    expect(points.map((p) => [p.kind, p.name])).toEqual([
      ['origin', '梅田（JR大阪駅）'],
      ['rent', 'A-01.梅田駅前'],
      ['return', 'B-02.なんば南'],
      ['destination', '地図で選んだ地点'],
    ])
    expect(lines.map((l) => l.mode)).toEqual(['walk', 'bike', 'walk'])
    expect(lines[1]?.positions).toHaveLength(3) // 直線ではなく経路の形状をそのまま使う
    expect(bounds.length).toBeGreaterThan(4)
  })

  it('経路がない：指定した地点だけを表示し、線は描かない（直線で結ばない）', () => {
    const { points, lines } = buildMapModel(origin, destination, null)
    expect(points.map((p) => p.kind)).toEqual(['origin', 'destination'])
    expect(lines).toEqual([])
  })

  it('片方だけ指定：その地点だけ', () => {
    expect(buildMapModel(null, destination, null).points.map((p) => p.kind)).toEqual(['destination'])
    expect(buildMapModel(null, null, null).bounds).toEqual([])
  })

  it('点が 1 つしかない geometry は線にしない', () => {
    const bike = bikeRoute.bike_share!
    const broken = { ...bike, legs: bike.legs.map((l) => ({ ...l, geometry: l.geometry.slice(0, 1) })) }
    expect(buildMapModel(origin, destination, broken).lines).toEqual([])
  })
})

describe('地図の配色と重なり（返却ポートと目的地を区別する）', () => {
  it('4 種類の点はすべて別の色で、配色の方針（青・緑・オレンジ・赤）に沿う', () => {
    const fills = LEGEND_ORDER.map((k) => MARKER_STYLE[k].fill)
    expect(new Set(fills).size).toBe(4)
    expect(MARKER_STYLE.origin.fill).toBe('#1d4ed8')
    expect(MARKER_STYLE.rent.fill).toBe(LINE_STYLE.bike.color) // 貸出ポートと自転車の線は同じ緑
    expect(MARKER_STYLE.return.fill).toBe('#fb923c')
    expect(MARKER_STYLE.destination.fill).toBe('#b91c1c')
    expect(LINE_STYLE.walk.color).toBe('#475569')
  })

  it('返却ポートは目的地と枠線の色も変え、枠を太くする', () => {
    expect(MARKER_STYLE.return.stroke).not.toBe(MARKER_STYLE.destination.stroke)
    expect(MARKER_STYLE.return.weight).toBeGreaterThan(MARKER_STYLE.destination.weight)
  })

  it('重なっても両方が見えるよう、目的地を大きく先に描き、返却ポートを上に描く', () => {
    expect(MARKER_STYLE.destination.radius).toBeGreaterThan(MARKER_STYLE.return.radius)
    const { points } = buildMapModel(origin, destination, bikeRoute.bike_share)
    const order = sortForDrawing(points).map((p) => p.kind)
    expect(order.indexOf('return')).toBeGreaterThan(order.indexOf('destination'))
    expect(order.indexOf('rent')).toBeGreaterThan(order.indexOf('origin'))
    expect(points.map((p) => p.kind)).toEqual(['origin', 'rent', 'return', 'destination']) // 元の配列は変えない
  })
})
