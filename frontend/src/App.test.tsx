import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { RouteResponse } from './api/types'
import { bikeRecommended, noBikeShare, presetsResponse, walkRecommended } from './test/fixtures'

// Leaflet は jsdom で描画できないため、地図は受け取った結果だけを表示する代用品に差し替える。
vi.mock('./RouteMap', () => ({
  default: ({ result }: { result: RouteResponse }) => (
    <div data-testid="route-map">
      {result.origin.name}→{result.destination.name}
    </div>
  ),
}))

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

type Handler = () => Promise<Response>

/** /api/presets は常に成功させ、検索 API の応答だけをテストごとに差し替える。 */
function mockApi(search?: Handler) {
  const fetchMock = vi.fn<typeof fetch>((input) => {
    const url = String(input)
    if (url.endsWith('/api/presets')) return Promise.resolve(json(presetsResponse))
    if (url.endsWith('/api/routes/search') && search) return search()
    return Promise.reject(new Error(`unexpected fetch: ${url}`))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function searchCalls(fetchMock: ReturnType<typeof mockApi>) {
  return fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/api/routes/search'))
}

async function selectRoute(originName: string, destinationName: string) {
  const user = userEvent.setup()
  await screen.findAllByRole('option', { name: originName })
  await user.selectOptions(screen.getByLabelText('出発地'), originName)
  await user.selectOptions(screen.getByLabelText('目的地'), destinationName)
  return user
}

async function searchFor(search: Handler) {
  const fetchMock = mockApi(search)
  render(<App />)
  const user = await selectRoute('梅田（JR大阪駅）', '難波（なんば駅）')
  await user.click(screen.getByRole('button', { name: '経路を検索' }))
  return { fetchMock, user }
}

describe('初期状態と入力', () => {
  beforeEach(() => {
    mockApi()
  })

  it('サービス名と案内、プリセットの選択肢を表示する', async () => {
    render(<App />)
    expect(screen.getByRole('heading', { level: 1, name: 'ChariRoute' })).toBeInTheDocument()
    expect(screen.getByText(/「経路を検索」を押してください/)).toBeInTheDocument()
    const origin = screen.getByLabelText('出発地')
    expect(await within(origin).findByRole('option', { name: '天王寺駅' })).toBeInTheDocument()
    expect(within(screen.getByLabelText('目的地')).getAllByRole('option')).toHaveLength(4)
  })

  it('概算であることと、公式アプリでの確認を促す注意書きを表示する', () => {
    render(<App />)
    expect(screen.getByText(/道路に沿った経路ではありません/)).toBeInTheDocument()
    expect(screen.getByText(/公式アプリ/)).toBeInTheDocument()
  })

  it('入れ替えボタンで出発地と目的地を入れ替える', async () => {
    render(<App />)
    const user = await selectRoute('梅田（JR大阪駅）', '天王寺駅')
    await user.click(screen.getByRole('button', { name: '出発地と目的地を入れ替える' }))
    expect(screen.getByLabelText('出発地')).toHaveValue('tennoji')
    expect(screen.getByLabelText('目的地')).toHaveValue('umeda')
  })

  it('未選択で検索すると入力エラーを表示し、API を呼ばない', async () => {
    const fetchMock = mockApi()
    const user = userEvent.setup()
    render(<App />)
    await screen.findAllByRole('option', { name: '天王寺駅' })
    await user.click(screen.getByRole('button', { name: '経路を検索' }))
    expect(screen.getByRole('alert')).toHaveTextContent('出発地と目的地を選択してください')
    expect(searchCalls(fetchMock)).toHaveLength(0)
  })

  it('同じ地点を選ぶと入力エラーを表示し、API を呼ばない', async () => {
    const fetchMock = mockApi()
    render(<App />)
    const user = await selectRoute('難波（なんば駅）', '難波（なんば駅）')
    await user.click(screen.getByRole('button', { name: '経路を検索' }))
    expect(screen.getByRole('alert')).toHaveTextContent('別の地点を選択してください')
    expect(searchCalls(fetchMock)).toHaveLength(0)
  })

  it('プリセットが 0 件ならエラーを表示し、検索できない', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json({ presets: [] }))))
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent('地点が登録されていません')
    expect(screen.getByRole('button', { name: '経路を検索' })).toBeDisabled()
  })

  it('プリセットの取得に失敗したらエラーを表示し、検索できない', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json({ detail: 'x' }, 500))))
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent('地点の一覧を読み込めませんでした')
    expect(screen.getByRole('button', { name: '経路を検索' })).toBeDisabled()
  })
})

describe('検索', () => {
  it('読み込み中は表示を切り替え、ボタンを無効にする', async () => {
    let resolve: (r: Response) => void = () => {}
    await searchFor(() => new Promise<Response>((r) => (resolve = r)))
    expect(screen.getByRole('status')).toHaveTextContent('経路を計算しています')
    expect(screen.getByRole('button', { name: '検索中…' })).toBeDisabled()
    // 検索中は選択を変えられない
    expect(screen.getByLabelText('出発地')).toBeDisabled()
    expect(screen.getByLabelText('目的地')).toBeDisabled()
    expect(screen.getByRole('button', { name: '出発地と目的地を入れ替える' })).toBeDisabled()

    resolve(json(bikeRecommended))
    expect(await screen.findByRole('heading', { name: 'おすすめ：シェアサイクル' })).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '経路を検索' })).toBeEnabled()
  })

  it('選んだ地点の id を POST で送る', async () => {
    const { fetchMock } = await searchFor(() => Promise.resolve(json(bikeRecommended)))
    await screen.findByRole('heading', { name: 'おすすめ：シェアサイクル' })
    const [url, init] = searchCalls(fetchMock)[0] ?? []
    expect(String(url)).toBe('/api/routes/search')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual({ origin_id: 'umeda', destination_id: 'namba' })
  })

  it('シェアサイクルがおすすめの結果：比較・内訳・ポート・地図・出典を表示する', async () => {
    await searchFor(() => Promise.resolve(json(bikeRecommended)))
    expect(await screen.findByRole('heading', { name: 'おすすめ：シェアサイクル' })).toBeInTheDocument()
    expect(screen.getByText('徒歩のみより 約41分 早く着く見込みです。')).toBeInTheDocument()

    // 比較
    expect(screen.getByText('約24分')).toBeInTheDocument()
    expect(screen.getByText('約65分')).toBeInTheDocument()

    // 内訳（徒歩 + 手続き + 自転車 + 手続き + 徒歩）
    const table = screen.getByRole('table')
    const rows = within(table).getAllByRole('row').map((r) => r.textContent)
    expect(rows).toEqual([
      '徒歩（出発地 → 貸出ポート）直線 52m0.9分',
      '貸出の手続き1.0分',
      '自転車（貸出 → 返却ポート）直線 3.9km20.3分',
      '返却の手続き1.0分',
      '徒歩（返却ポート → 目的地）直線 72m1.2分',
      '合計24.4分',
    ])

    // ポートと台数
    expect(screen.getByText('A-01.梅田駅前')).toBeInTheDocument()
    expect(screen.getByText('空き自転車 7台')).toBeInTheDocument()
    expect(screen.getByText('B-02.なんば南')).toBeInTheDocument()
    expect(screen.getByText('空きドック 11台')).toBeInTheDocument()

    // 地図には検索結果を渡す
    expect(screen.getByTestId('route-map')).toHaveTextContent('梅田（JR大阪駅）→難波（なんば駅）')

    // 取得時刻・出典・ライセンス
    expect(screen.getByText(/2026\/11\/25 18:30:15/)).toBeInTheDocument()
    expect(screen.getByText(/出典：株式会社ドコモ・バイクシェア/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'CC BY 4.0' })).toHaveAttribute(
      'href',
      'https://creativecommons.org/licenses/by/4.0/deed.ja',
    )
  })

  it('徒歩がおすすめの結果：シェアサイクルの所要時間も並べて表示する', async () => {
    await searchFor(() => Promise.resolve(json(walkRecommended)))
    expect(await screen.findByRole('heading', { name: 'おすすめ：徒歩のみ' })).toBeInTheDocument()
    expect(screen.getByText(/シェアサイクルを使っても徒歩より早くなりません/)).toBeInTheDocument()
    expect(screen.getByText('約70分')).toBeInTheDocument()
    expect(screen.getByText('約65分')).toBeInTheDocument()
  })

  it('シェアサイクルの経路がない場合：徒歩のみを示し、ポートや内訳を出さない', async () => {
    await searchFor(() => Promise.resolve(json(noBikeShare)))
    expect(await screen.findByRole('heading', { name: 'おすすめ：徒歩のみ' })).toBeInTheDocument()
    expect(screen.getByText(/組み合わせが見つかりませんでした/)).toBeInTheDocument()
    expect(screen.getByText('利用できません')).toBeInTheDocument()
    expect(screen.getByText('約65分')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByText(/空き自転車/)).not.toBeInTheDocument()
    expect(screen.getByText(/出典：株式会社ドコモ・バイクシェア/)).toBeInTheDocument()
  })
})

describe('検索の失敗（ダミーの結果を出さない）', () => {
  function expectNoResult() {
    expect(screen.queryByRole('heading', { name: /おすすめ/ })).not.toBeInTheDocument()
    expect(screen.queryByText(/約\d+分/)).not.toBeInTheDocument()
    expect(screen.queryByTestId('route-map')).not.toBeInTheDocument()
  }

  it('503（GBFS の取得失敗）：「ポート情報を取得できません」と表示する', async () => {
    await searchFor(() =>
      Promise.resolve(
        json({ detail: 'ポート情報を取得できませんでした。しばらくしてから再度お試しください' }, 503),
      ),
    )
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('ポート情報を取得できません')
    expect(alert).toHaveTextContent('しばらくしてから再度お試しください')
    expectNoResult()
  })

  it('400：サーバーの detail を入力エラーとして表示する', async () => {
    await searchFor(() => Promise.resolve(json({ detail: '指定された地点が見つかりません' }, 400)))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('入力内容を確認してください')
    expect(alert).toHaveTextContent('指定された地点が見つかりません')
    expectNoResult()
  })

  it('422：形式エラーとして表示する', async () => {
    await searchFor(() =>
      Promise.resolve(json({ detail: [{ loc: ['body', 'origin_id'], msg: 'x', type: 'y' }] }, 422)),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('入力内容の形式が正しくありません')
    expectNoResult()
  })

  it('通信障害：通信エラーを表示する', async () => {
    await searchFor(() => Promise.reject(new TypeError('Failed to fetch')))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('通信エラー')
    expect(alert).toHaveTextContent('サーバーに接続できませんでした')
    expectNoResult()
  })

  it('500：サーバーエラーを表示する', async () => {
    await searchFor(() => Promise.resolve(new Response('Internal Server Error', { status: 500 })))
    expect(await screen.findByRole('alert')).toHaveTextContent('HTTP 500')
    expectNoResult()
  })

  it('200 でも想定外の本文ならエラーにする', async () => {
    await searchFor(() => Promise.resolve(json({ recommended: 'car' })))
    expect(await screen.findByRole('alert')).toHaveTextContent('想定外の応答')
    expectNoResult()
  })

  it('200 でもポートの項目が欠けていればエラーにする（画面を壊さない）', async () => {
    const broken = { ...bikeRecommended, bike_share: { total_minutes: 24.4 } }
    await searchFor(() => Promise.resolve(json(broken)))
    expect(await screen.findByRole('alert')).toHaveTextContent('想定外の応答')
    expectNoResult()
  })

  it('成功のあとに失敗したら、前回の結果を残さない', async () => {
    const responses = [json(bikeRecommended), json({ detail: '取得失敗' }, 503)]
    const { user } = await searchFor(() => Promise.resolve(responses.shift()!))
    await screen.findByRole('heading', { name: 'おすすめ：シェアサイクル' })
    await user.click(screen.getByRole('button', { name: '経路を検索' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('ポート情報を取得できません')
    expectNoResult()
  })
})
