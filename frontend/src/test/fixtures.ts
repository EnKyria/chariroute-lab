// テスト用のレスポンス。型注釈により、backend と同じ構造（src/api/types.ts）であることをコンパイル時に確かめる。
import type { PlacesResponse, PresetsResponse, RouteResponse } from '../api/types'

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
  routing: {
    provider: 'OSRM / FOSSGIS（routing.openstreetmap.de）',
    provider_url: 'https://routing.openstreetmap.de/about.html',
    map_data: '© OpenStreetMap contributors（ODbL）',
    map_data_url: 'https://www.openstreetmap.org/copyright',
    fixthemap_url: 'https://www.openstreetmap.org/fixthemap',
  },
}

export const bikeRoute: RouteResponse = {
  origin: { name: '梅田（JR大阪駅）', lat: 34.7025, lon: 135.4959, source: 'preset', preset_id: 'umeda' },
  destination: { name: '難波（なんば駅）', lat: 34.6666, lon: 135.5008, source: 'preset', preset_id: 'namba' },
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
    legs: [
      {
        mode: 'walk',
        distance_m: 80,
        minutes: 1.0,
        geometry: [
          [34.7025, 135.4959],
          [34.7021, 135.4962],
        ],
      },
      {
        mode: 'bike',
        distance_m: 4250,
        minutes: 17.0,
        geometry: [
          [34.7021, 135.4962],
          [34.685, 135.499],
          [34.6671, 135.5003],
        ],
      },
      {
        mode: 'walk',
        distance_m: 120,
        minutes: 1.5,
        geometry: [
          [34.6671, 135.5003],
          [34.6666, 135.5008],
        ],
      },
    ],
    rent_minutes: 1.0,
    return_minutes: 1.0,
    total_minutes: 21.5,
  },
  search: { rent_candidates: 11, return_candidates: 10, pairs_evaluated: 110 },
  data,
}

export const noBikeShare: RouteResponse = {
  ...bikeRoute,
  bike_share: null,
}

export const placesResponse: PlacesResponse = {
  places: [
    { name: '大阪城天守閣', label: '大阪城天守閣, 中央区, 大阪市', lat: 34.6873, lon: 135.5262 },
    { name: '大阪城公園駅', label: '大阪城公園駅, 中央区, 大阪市', lat: 34.6881, lon: 135.5338 },
  ],
  attribution: '地点検索：Nominatim / © OpenStreetMap contributors（ODbL）',
}
