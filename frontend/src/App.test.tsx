import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { BikeShareRoute } from './api/types'
import type { SelectedPoint } from './points'
import type { PickTarget } from './RouteMap'
import { bikeRoute, noBikeShare, placesResponse, presetsResponse } from './test/fixtures'

// Leaflet は jsdom で描画できないため、地図は代用品に差し替える。
// 「地図をタップ」ボタンで、指定中の地点に座標を渡す（タップの代わり）。
vi.mock('./RouteMap', () => ({
  default: (props: {
    origin: SelectedPoint | null
    destination: SelectedPoint | null
    bike: BikeShareRoute | null
    pickTarget: PickTarget | null
    onPick: (t: PickTarget, lat: number, lon: number) => void
  }) => (
    <div data-testid="route-map">
      <span>地図の線：{props.bike ? props.bike.legs.length : 0}本</span>
      <button type="button" onClick={() => props.pickTarget && props.onPick(props.pickTarget, 34.69, 135.51)}>
        地図をタップ（大阪）
      </button>
      <button type="button" onClick={() => props.pickTarget && props.onPick(props.pickTarget, 35.68, 139.76)}>
        地図をタップ（東京）
      </button>
    </div>
  ),
}))

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

type Handler = (init?: RequestInit) => Promise<Response>

/** /api/presets は常に成功させ、検索 API・地点検索 API の応答だけをテストごとに差し替える。 */
function mockApi(search?: Handler, places?: Handler) {
  const fetchMock = vi.fn<typeof fetch>((input, init) => {
    const url = String(input)
    if (url.endsWith('/api/presets')) return Promise.resolve(json(presetsResponse))
    if (url.endsWith('/api/routes/search') && search) return search(init)
    if (url.endsWith('/api/places/search') && places) return places(init)
    return Promise.reject(new Error(`unexpected fetch: ${url}`))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function calls(fetchMock: ReturnType<typeof mockApi>, path: string) {
  return fetchMock.mock.calls.filter(([url]) => String(url).endsWith(path))
}

function bodyOf(call: Parameters<typeof fetch> | undefined): unknown {
  return JSON.parse(String(call?.[1]?.body))
}

async function choosePresets(originName: string, destinationName: string) {
  const user = userEvent.setup()
  await screen.findAllByRole('option', { name: originName })
  await user.selectOptions(screen.getByLabelText('出発地のプリセット'), originName)
  await user.selectOptions(screen.getByLabelText('目的地のプリセット'), destinationName)
  return user
}

async function searchFor(search: Handler) {
  const fetchMock = mockApi(search)
  render(<App />)
  const user = await choosePresets('梅田（JR大阪駅）', '難波（なんば駅）')
  await user.click(screen.getByRole('button', { name: '経路を検索' }))
  return { fetchMock, user }
}

function picker(name: '出発地' | '目的地') {
  return within(screen.getByRole('group', { name }))
}

// --- Geolocation の差し替え ----------------------------------------------------------
type GeoMock = { getCurrentPosition: ReturnType<typeof vi.fn> }

function setGeolocation(geo: GeoMock | undefined, secure = true) {
  Object.defineProperty(window, 'isSecureContext', { value: secure, configurable: true })
  Object.defineProperty(navigator, 'geolocation', { value: geo, configurable: true })
}

function geoSuccess(lat: number, lon: number): GeoMock {
  return {
    getCurrentPosition: vi.fn((ok: PositionCallback) =>
      ok({ coords: { latitude: lat, longitude: lon } } as GeolocationPosition),
    ),
  }
}

function geoFailure(code: number): GeoMock {
  return {
    getCurrentPosition: vi.fn((_ok: PositionCallback, fail: PositionErrorCallback) =>
      fail({ code } as GeolocationPositionError),
    ),
  }
}

afterEach(() => {
  setGeolocation(undefined)
})

describe('初期状態と入力', () => {
  beforeEach(() => {
    mockApi()
  })

  it('サービス名、地点の指定方法、プリセットの選択肢を表示する', async () => {
    render(<App />)
    expect(screen.getByRole('heading', { level: 1, name: 'ChariRoute' })).toBeInTheDocument()
    expect(screen.getByText(/「経路を検索」を押してください/)).toBeInTheDocument()
    const origin = picker('出発地')
    expect(await origin.findByRole('option', { name: '天王寺駅' })).toBeInTheDocument()
    expect(origin.getByRole('button', { name: '現在地' })).toBeInTheDocument()
    expect(origin.getByRole('button', { name: '地図で選ぶ' })).toBeInTheDocument()
    expect(origin.getByRole('button', { name: '地点検索' })).toBeInTheDocument()
  })

  it('FE-10：検索ボタンの近くに、座標を FOSSGIS（ドイツ）に送ることとログに残ることを明示する', () => {
    render(<App />)
    expect(screen.getByText(/FOSSGIS の OSRM、ドイツ/)).toBeInTheDocument()
    expect(screen.getByText(/FOSSGIS のサーバーログに記録されます/)).toBeInTheDocument()
  })

  it('FE-9：推定値であること、全体の最適解を保証しないこと、公式アプリでの確認を注意書きに出す', () => {
    render(<App />)
    expect(screen.getByText(/実測ではありません/)).toBeInTheDocument()
    expect(screen.getByText(/最適解は保証しません/)).toBeInTheDocument()
    expect(screen.getByText(/公式アプリ/)).toBeInTheDocument()
  })

  it('フッターに運営者の連絡先（mailto）と帰属表示を出す', () => {
    render(<App />)
    const mail = screen.getByRole('link', { name: 'chariroute.dev@gmail.com' })
    expect(mail).toHaveAttribute('href', 'mailto:chariroute.dev@gmail.com')
    const footer = screen.getByRole('contentinfo')
    expect(within(footer).getByText(/OSRM \/ FOSSGIS/)).toBeInTheDocument()
    expect(within(footer).getByText(/Nominatim/)).toBeInTheDocument()
    expect(within(footer).getByRole('link', { name: '地図の誤りを報告' })).toHaveAttribute(
      'href',
      'https://www.openstreetmap.org/fixthemap',
    )
  })

  it('FE-5：入れ替えボタンで出発地と目的地を入れ替える（片方が未指定でも壊れない）', async () => {
    render(<App />)
    const user = userEvent.setup()
    await screen.findAllByRole('option', { name: '天王寺駅' })
    await user.selectOptions(screen.getByLabelText('出発地のプリセット'), '天王寺駅')
    await user.click(screen.getByRole('button', { name: '出発地と目的地を入れ替える' }))
    expect(screen.getByTestId('origin-picked')).toHaveTextContent('未指定')
    expect(screen.getByTestId('destination-picked')).toHaveTextContent('天王寺駅')
  })

  it('未指定で検索すると入力エラーを表示し、API を呼ばない', async () => {
    const fetchMock = mockApi()
    render(<App />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '経路を検索' }))
    expect(screen.getByRole('alert')).toHaveTextContent('出発地と目的地を指定してください')
    expect(calls(fetchMock, '/api/routes/search')).toHaveLength(0)
  })

  it('同じ地点を選ぶと入力エラーを表示し、API を呼ばない', async () => {
    const fetchMock = mockApi()
    render(<App />)
    const user = await choosePresets('天王寺駅', '天王寺駅')
    await user.click(screen.getByRole('button', { name: '経路を検索' }))
    expect(screen.getByRole('alert')).toHaveTextContent('別の地点を指定してください')
    expect(calls(fetchMock, '/api/routes/search')).toHaveLength(0)
  })
})

describe('地点の指定', () => {
  it('FE-4：プリセットは preset_id で送る', async () => {
    const { fetchMock } = await searchFor(() => Promise.resolve(json(bikeRoute)))
    expect(bodyOf(calls(fetchMock, '/api/routes/search')[0])).toEqual({
      origin: { preset_id: 'umeda' },
      destination: { preset_id: 'namba' },
    })
  })

  it('FE-3：地図で選ぶ → タップで source=map の座標が入る', async () => {
    const fetchMock = mockApi(() => Promise.resolve(json(bikeRoute)))
    render(<App />)
    const user = userEvent.setup()
    await user.click(picker('目的地').getByRole('button', { name: '地図で選ぶ' }))
    await user.click(screen.getByRole('button', { name: '地図をタップ（大阪）' }))
    expect(screen.getByTestId('destination-picked')).toHaveTextContent('地図で選んだ地点')
    await user.selectOptions(screen.getByLabelText('出発地のプリセット'), '天王寺駅')
    await user.click(screen.getByRole('button', { name: '経路を検索' }))
    expect(bodyOf(calls(fetchMock, '/api/routes/search')[0])).toEqual({
      origin: { preset_id: 'tennoji' },
      destination: { lat: 34.69, lon: 135.51, source: 'map' },
    })
  })

  it('地図で対象エリアの外をタップするとエラーを表示し、地点を設定しない', async () => {
    mockApi()
    render(<App />)
    const user = userEvent.setup()
    await user.click(picker('出発地').getByRole('button', { name: '地図で選ぶ' }))
    await user.click(screen.getByRole('button', { name: '地図をタップ（東京）' }))
    expect(screen.getByRole('alert')).toHaveTextContent('大阪市の周辺の地点を指定してください')
    expect(screen.getByTestId('origin-picked')).toHaveTextContent('未指定')
  })

  it('FE-1：現在地はボタンを押したときだけ取得し、source=gps で送る', async () => {
    const geo = geoSuccess(34.7, 135.5)
    setGeolocation(geo)
    const fetchMock = mockApi(() => Promise.resolve(json(bikeRoute)))
    render(<App />)
    expect(geo.getCurrentPosition).not.toHaveBeenCalled()
    const user = userEvent.setup()
    await user.click(picker('出発地').getByRole('button', { name: '現在地' }))
    expect(geo.getCurrentPosition).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('origin-picked')).toHaveTextContent('現在地')
    await user.selectOptions(screen.getByLabelText('目的地のプリセット'), '難波（なんば駅）')
    await user.click(screen.getByRole('button', { name: '経路を検索' }))
    expect(bodyOf(calls(fetchMock, '/api/routes/search')[0])).toEqual({
      origin: { lat: 34.7, lon: 135.5, source: 'gps' },
      destination: { preset_id: 'namba' },
    })
  })

  it.each([
    ['denied', () => setGeolocation(geoFailure(1)), /許可されていません/],
    ['unavailable', () => setGeolocation(geoFailure(2)), /現在地を取得できませんでした/],
    ['timeout', () => setGeolocation(geoFailure(3)), /タイムアウト/],
    ['unsupported', () => setGeolocation(undefined), /対応していません/],
    ['insecure', () => setGeolocation(geoSuccess(34.7, 135.5), false), /HTTPS/],
    ['outside', () => setGeolocation(geoSuccess(35.68, 139.76)), /対象エリアの外/],
  ])('FE-2：現在地の取得の失敗（%s）をそれぞれの文言で表示する', async (_name, setup, message) => {
    setup()
    mockApi()
    render(<App />)
    const user = userEvent.setup()
    await user.click(picker('出発地').getByRole('button', { name: '現在地' }))
    expect(await picker('出発地').findByRole('alert')).toHaveTextContent(message)
    expect(screen.getByTestId('origin-picked')).toHaveTextContent('未指定')
  })

  it('現在地の取得中に別の地点を指定したら、遅れて届いた現在地で上書きしない', async () => {
    let deliver: () => void = () => {}
    setGeolocation({
      getCurrentPosition: vi.fn((ok: PositionCallback) => {
        deliver = () => ok({ coords: { latitude: 34.7, longitude: 135.5 } } as GeolocationPosition)
      }),
    })
    mockApi()
    render(<App />)
    const user = userEvent.setup()
    await screen.findAllByRole('option', { name: '天王寺駅' })
    await user.click(picker('出発地').getByRole('button', { name: '現在地' }))
    await user.selectOptions(screen.getByLabelText('出発地のプリセット'), '天王寺駅')
    await act(async () => deliver())
    expect(screen.getByTestId('origin-picked')).toHaveTextContent('天王寺駅')
    expect(picker('出発地').getByRole('button', { name: '現在地' })).toBeEnabled()
  })

  it('FE-14：地点検索はボタンを押したときだけ POST で送り、選んだ候補を source=place で使う', async () => {
    const fetchMock = mockApi(
      () => Promise.resolve(json(bikeRoute)),
      () => Promise.resolve(json(placesResponse)),
    )
    render(<App />)
    const user = userEvent.setup()
    await user.click(picker('目的地').getByRole('button', { name: '地点検索' }))
    expect(screen.getByText(/個人名・住所・電話番号などは入力しないでください/)).toBeInTheDocument()
    await user.type(screen.getByLabelText('目的地を検索（駅名・施設名）'), '大阪城')
    expect(calls(fetchMock, '/api/places/search')).toHaveLength(0) // 入力中は送らない
    await user.click(picker('目的地').getByRole('button', { name: '検索' }))
    const placeCalls = calls(fetchMock, '/api/places/search')
    expect(placeCalls).toHaveLength(1)
    expect(placeCalls[0]?.[1]?.method).toBe('POST')
    expect(bodyOf(placeCalls[0])).toEqual({ q: '大阪城' })
    await user.click(await screen.findByRole('button', { name: /大阪城天守閣/ }))
    expect(screen.getByTestId('destination-picked')).toHaveTextContent('大阪城天守閣')
    await user.selectOptions(screen.getByLabelText('出発地のプリセット'), '天王寺駅')
    await user.click(screen.getByRole('button', { name: '経路を検索' }))
    expect(bodyOf(calls(fetchMock, '/api/routes/search')[0])).toEqual({
      origin: { preset_id: 'tennoji' },
      destination: { lat: 34.6873, lon: 135.5262, source: 'place', name: '大阪城天守閣' },
    })
  })

  it('地点検索：1 文字では送らず、失敗（503）と 0 件をそれぞれ表示する', async () => {
    let reply: () => Promise<Response> = () =>
      Promise.resolve(json({ detail: '地点を検索できませんでした。しばらくしてから再度お試しください', code: 'places_unavailable' }, 503))
    const fetchMock = mockApi(undefined, () => reply())
    render(<App />)
    const user = userEvent.setup()
    await user.click(picker('出発地').getByRole('button', { name: '地点検索' }))
    const input = screen.getByLabelText('出発地を検索（駅名・施設名）')
    await user.type(input, '駅')
    await user.click(picker('出発地').getByRole('button', { name: '検索' }))
    expect(picker('出発地').getByRole('alert')).toHaveTextContent('2〜64 文字')
    expect(calls(fetchMock, '/api/places/search')).toHaveLength(0)
    await user.type(input, '前')
    await user.click(picker('出発地').getByRole('button', { name: '検索' }))
    expect(await picker('出発地').findByRole('alert')).toHaveTextContent('地点を検索できませんでした')
    reply = () => Promise.resolve(json({ places: [], attribution: 'x' }))
    await user.click(picker('出発地').getByRole('button', { name: '検索' }))
    expect(await screen.findByText(/見つかりませんでした。別の駅名/)).toBeInTheDocument()
  })
})

describe('検索結果', () => {
  it('読み込み中は表示を切り替え、ボタンを無効にする', async () => {
    let resolve: (r: Response) => void = () => {}
    await searchFor(() => new Promise<Response>((r) => (resolve = r)))
    expect(screen.getByRole('status')).toHaveTextContent('道路に沿った経路を計算しています')
    expect(screen.getByRole('button', { name: '検索中…' })).toBeDisabled()
    resolve(json(bikeRoute))
    expect(await screen.findByRole('heading', { name: /推定所要時間 約22分/ })).toBeInTheDocument()
  })

  it('FE-8：3 区間の道路距離と推定時間、合計、ポートと台数、取得時刻、帰属表示を出す', async () => {
    await searchFor(() => Promise.resolve(json(bikeRoute)))
    const result = await screen.findByRole('region', { name: '検索結果' })
    const r = within(result)
    expect(r.getByRole('heading', { name: '推定所要時間 約22分' })).toBeInTheDocument()
    const rows = r.getAllByRole('row').map((row) => row.textContent)
    expect(rows).toEqual([
      '徒歩（出発地 → 貸出ポート）道路距離 80m1.0分',
      '貸出の手続き1.0分',
      '自転車（貸出 → 返却ポート）道路距離 4.3km17.0分',
      '返却の手続き1.0分',
      '徒歩（返却ポート → 目的地）道路距離 120m1.5分',
      '合計（推定）21.5分',
    ])
    expect(r.getByText('空き自転車 7台')).toBeInTheDocument()
    expect(r.getByText('空きドック 11台')).toBeInTheDocument()
    expect(r.getByText(/2026\/11\/25 18:30:15/)).toBeInTheDocument()
    expect(r.getByText(/公共交通オープンデータ協議会/)).toBeInTheDocument()
    expect(r.getByRole('link', { name: /OSRM \/ FOSSGIS/ })).toBeInTheDocument()
    expect(r.getByRole('link', { name: /地図の誤りを報告/ })).toHaveAttribute(
      'href',
      'https://www.openstreetmap.org/fixthemap',
    )
    expect(screen.getByText('地図の線：3本')).toBeInTheDocument()
    // 廃止した機能（徒歩との比較・おすすめ・短縮効果）を表示しない
    for (const word of [/おすすめ/, /徒歩のみ/, /早く着く/, /比較/]) {
      expect(screen.queryByText(word)).not.toBeInTheDocument()
    }
  })

  it('FE-7：経路がない場合は「見つかりませんでした」と表示し、ポートや内訳を出さない', async () => {
    await searchFor(() => Promise.resolve(json(noBikeShare)))
    expect(
      await screen.findByRole('heading', { name: '利用できるシェアサイクルの経路が見つかりませんでした' }),
    ).toBeInTheDocument()
    expect(screen.queryByText('利用するポート')).not.toBeInTheDocument()
    expect(screen.queryByText(/徒歩のみ/)).not.toBeInTheDocument()
    expect(screen.getByText('地図の線：0本')).toBeInTheDocument()
  })

  it('地点を変えたら、前の結果を消す', async () => {
    const { user } = await searchFor(() => Promise.resolve(json(bikeRoute)))
    await screen.findByRole('region', { name: '検索結果' })
    await user.selectOptions(screen.getByLabelText('目的地のプリセット'), '天王寺駅')
    expect(screen.queryByRole('region', { name: '検索結果' })).not.toBeInTheDocument()
  })

  it('FE-12：localStorage / sessionStorage に書き込まない', async () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem')
    setGeolocation(geoSuccess(34.7, 135.5))
    mockApi(() => Promise.resolve(json(bikeRoute)))
    render(<App />)
    const user = userEvent.setup()
    await user.click(picker('出発地').getByRole('button', { name: '現在地' }))
    await screen.findAllByRole('option', { name: '天王寺駅' })
    await user.selectOptions(screen.getByLabelText('目的地のプリセット'), '天王寺駅')
    await user.click(screen.getByRole('button', { name: '経路を検索' }))
    await screen.findByRole('region', { name: '検索結果' })
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
  })
})

describe('検索の失敗（ダミーの結果を出さない）', () => {
  it.each([
    ['gbfs_unavailable', 'ポート情報を取得できません', 'ポート情報を取得できませんでした'],
    ['route_unavailable', '道路の経路を取得できません', '道路の経路を取得できませんでした'],
    ['route_busy', '混雑しています', '経路サービスが混雑しています'],
  ])('FE-6：503（%s）を区別して表示する', async (code, title, detail) => {
    await searchFor(() =>
      Promise.resolve(json({ detail: `${detail}。しばらくしてから再度お試しください`, code }, 503)),
    )
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByRole('heading')).toHaveTextContent(title)
    expect(alert).toHaveTextContent(detail)
    expect(screen.queryByText(/推定所要時間 約/)).not.toBeInTheDocument()
    expect(screen.queryByText(/徒歩のみ/)).not.toBeInTheDocument()
  })

  it('503 で code がなければ、経路の取得失敗として扱う', async () => {
    await searchFor(() => Promise.resolve(new Response('Service Unavailable', { status: 503 })))
    expect(await screen.findByRole('alert')).toHaveTextContent('道路の経路を取得できません')
  })

  it('400：サーバーの detail を入力エラーとして表示する', async () => {
    await searchFor(() =>
      Promise.resolve(json({ detail: '目的地の近くに道路が見つかりません。別の地点を指定してください', code: 'no_road_nearby' }, 400)),
    )
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('入力内容を確認してください')
    expect(alert).toHaveTextContent('近くに道路が見つかりません')
  })

  it('422：形式エラーとして表示する', async () => {
    await searchFor(() => Promise.resolve(json({ detail: [], code: 'invalid_request' }, 422)))
    expect(await screen.findByRole('alert')).toHaveTextContent('入力内容の形式が正しくありません')
  })

  it('通信障害：通信エラーを表示する', async () => {
    await searchFor(() => Promise.reject(new TypeError('Failed to fetch')))
    expect(await screen.findByRole('alert')).toHaveTextContent('通信エラー')
  })

  it('504（API Gateway のタイムアウト）：道路の経路を取得できないとして表示する', async () => {
    await searchFor(() => Promise.resolve(json({ message: 'Service Unavailable' }, 504)))
    expect(await screen.findByRole('alert')).toHaveTextContent('時間内に取得できませんでした')
  })

  it('500：サーバーエラーを表示する', async () => {
    await searchFor(() => Promise.resolve(json({ detail: 'Internal Server Error' }, 500)))
    expect(await screen.findByRole('alert')).toHaveTextContent('HTTP 500')
  })

  it('200 でも想定外の本文（旧形式など）ならエラーにする', async () => {
    const legacy = { ...bikeRoute, bike_share: { ...bikeRoute.bike_share!, legs: undefined } }
    await searchFor(() => Promise.resolve(json(legacy)))
    expect(await screen.findByRole('alert')).toHaveTextContent('想定外の応答')
  })

  it('通信エラーのあと、同じ条件でもう一度検索できる（入力は保持し、結果に置き換わる）', async () => {
    let reply: Handler = () => Promise.reject(new TypeError('Failed to fetch'))
    const { fetchMock, user } = await searchFor(() => reply())
    expect(await screen.findByRole('alert')).toHaveTextContent('通信エラー')
    const button = screen.getByRole('button', { name: '経路を検索' })
    expect(button).toBeEnabled()
    expect(screen.getByTestId('origin-picked')).toHaveTextContent('梅田（JR大阪駅）')
    reply = () => Promise.resolve(json(bikeRoute))
    await user.click(button)
    expect(await screen.findByRole('region', { name: '検索結果' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(calls(fetchMock, '/api/routes/search')).toHaveLength(2) // 自動リトライはしない（押した回数だけ）
  })

  it('応答が 35 秒ない場合は打ち切って「応答がありませんでした」と表示し、再検索できる', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      const fetchMock = mockApi((init) => new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
      }))
      render(<App />)
      const user = await choosePresets('梅田（JR大阪駅）', '難波（なんば駅）')
      await user.click(screen.getByRole('button', { name: '経路を検索' }))
      expect(screen.getByRole('button', { name: '検索中…' })).toBeDisabled()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(35_000)
      })
      const alert = await screen.findByRole('alert')
      expect(alert).toHaveTextContent('通信エラー')
      expect(alert).toHaveTextContent('応答がありませんでした')
      expect(screen.getByRole('button', { name: '経路を検索' })).toBeEnabled()
      expect(calls(fetchMock, '/api/routes/search')).toHaveLength(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('成功のあとに失敗したら、前回の結果を残さない', async () => {
    let reply = () => Promise.resolve(json(bikeRoute))
    const { user } = await searchFor(() => reply())
    await screen.findByRole('region', { name: '検索結果' })
    reply = () => Promise.resolve(json({ detail: 'x', code: 'route_unavailable' }, 503))
    await user.click(screen.getByRole('button', { name: '経路を検索' }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: '検索結果' })).not.toBeInTheDocument()
  })
})
