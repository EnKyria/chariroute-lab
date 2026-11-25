import { describe, expect, it } from 'vitest'
import { buildMapModel } from './mapPoints'
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
