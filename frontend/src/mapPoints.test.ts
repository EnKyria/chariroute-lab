import { describe, expect, it } from 'vitest'
import { buildMapModel } from './mapPoints'
import { bikeRecommended, noBikeShare } from './test/fixtures'

describe('buildMapModel', () => {
  it('シェアサイクルの経路：4 地点を順に、自転車区間だけ bike で結ぶ', () => {
    const { points, segments } = buildMapModel(bikeRecommended)
    expect(points.map((p) => [p.kind, p.name])).toEqual([
      ['origin', '梅田（JR大阪駅）'],
      ['rent', 'A-01.梅田駅前'],
      ['return', 'B-02.なんば南'],
      ['destination', '難波（なんば駅）'],
    ])
    expect(segments.map((s) => s.mode)).toEqual(['walk', 'bike', 'walk'])
    expect(segments[1]).toEqual({ mode: 'bike', from: [34.7021, 135.4962], to: [34.6671, 135.5003] })
  })

  it('シェアサイクルの経路がない：出発地と目的地を徒歩で結ぶ', () => {
    const { points, segments } = buildMapModel(noBikeShare)
    expect(points.map((p) => p.kind)).toEqual(['origin', 'destination'])
    expect(segments).toEqual([{ mode: 'walk', from: [34.7025, 135.4959], to: [34.6666, 135.5008] }])
  })
})
