// テスト用のレスポンス。型注釈により、backend と同じ構造（src/api/types.ts）であることをコンパイル時に確かめる。
import type { PresetsResponse, RouteResponse } from '../api/types'

export const presetsResponse: PresetsResponse = {
  presets: [
    { id: 'umeda', name: '梅田（JR大阪駅）', lat: 34.7025, lon: 135.4959 },
    { id: 'namba', name: '難波（なんば駅）', lat: 34.6666, lon: 135.5008 },
    { id: 'tennoji', name: '天王寺駅', lat: 34.6466, lon: 135.5139 },
  ],
}

const data: RouteResponse['data'] = {
  last_updated: '2026-11-25T18:30:15+09:00',
  provider: '株式会社ドコモ・バイクシェア',
  source: '公共交通オープンデータ協議会（ODPT）',
  license: 'CC BY 4.0',
  license_url: 'https://creativecommons.org/licenses/by/4.0/deed.ja',
  attribution:
    '出典：株式会社ドコモ・バイクシェア / 公共交通オープンデータ協議会（CC BY 4.0）のポート情報を加工して作成',
  dataset_url: 'https://ckan.odpt.org/dataset/c_bikeshare_gbfs-d-nationwide-bikeshare',
}

export const bikeRecommended: RouteResponse = {
  origin: { id: 'umeda', name: '梅田（JR大阪駅）', lat: 34.7025, lon: 135.4959 },
  destination: { id: 'namba', name: '難波（なんば駅）', lat: 34.6666, lon: 135.5008 },
  recommended: 'bike_share',
  bike_share: {
    rent_station: {
      station_id: '1001',
      name: 'A-01.梅田駅前',
      lat: 34.7021,
      lon: 135.4962,
      num_bikes_available: 7,
      num_docks_available: 3,
    },
    return_station: {
      station_id: '2002',
      name: 'B-02.なんば南',
      lat: 34.6671,
      lon: 135.5003,
      num_bikes_available: 2,
      num_docks_available: 11,
    },
    walk_to_rent_m: 52.3,
    bike_m: 3912.4,
    walk_from_return_m: 71.8,
    walk_to_rent_minutes: 0.9,
    rent_minutes: 1.0,
    bike_minutes: 20.3,
    return_minutes: 1.0,
    walk_from_return_minutes: 1.2,
    total_minutes: 24.4,
  },
  walk: { distance_m: 4013.2, total_minutes: 65.2 },
  data,
}

export const walkRecommended: RouteResponse = {
  ...bikeRecommended,
  recommended: 'walk',
  bike_share: {
    ...bikeRecommended.bike_share!,
    total_minutes: 70.1,
  },
}

export const noBikeShare: RouteResponse = {
  ...bikeRecommended,
  recommended: 'walk',
  bike_share: null,
}
