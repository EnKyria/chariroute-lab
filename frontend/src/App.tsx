import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError, fetchPresets, searchRoute } from './api/client'
import type { BikeShareRoute, Preset, RouteResponse } from './api/types'
import RouteMap from './RouteMap'
import { formatDateTime, formatDistance, formatMinutes } from './format'

type PresetsState =
  | { status: 'loading' }
  | { status: 'ready'; presets: Preset[] }
  | { status: 'error'; message: string }

type SearchState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; result: RouteResponse }
  | { status: 'error'; error: ApiError }

function messageOf(e: unknown): ApiError {
  return e instanceof ApiError ? e : new ApiError('server', '予期しないエラーが発生しました')
}

export default function App() {
  const [presets, setPresets] = useState<PresetsState>({ status: 'loading' })
  const [originId, setOriginId] = useState('')
  const [destinationId, setDestinationId] = useState('')
  const [inputError, setInputError] = useState<string | null>(null)
  const [search, setSearch] = useState<SearchState>({ status: 'idle' })
  // 連続して検索したときに、古い応答で新しい結果を上書きしないための番号
  const latestRequest = useRef(0)

  useEffect(() => {
    let active = true
    fetchPresets()
      .then((res) => {
        if (!active) return
        if (res.presets.length === 0) setPresets({ status: 'error', message: '地点が登録されていません' })
        else setPresets({ status: 'ready', presets: res.presets })
      })
      .catch((e: unknown) => active && setPresets({ status: 'error', message: messageOf(e).message }))
    return () => {
      active = false
    }
  }, [])

  function swap() {
    setOriginId(destinationId)
    setDestinationId(originId)
    setInputError(null)
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!originId || !destinationId) {
      setInputError('出発地と目的地を選択してください')
      return
    }
    if (originId === destinationId) {
      setInputError('出発地と目的地に別の地点を選択してください')
      return
    }
    setInputError(null)
    const id = ++latestRequest.current
    setSearch({ status: 'loading' })
    try {
      const result = await searchRoute({ origin_id: originId, destination_id: destinationId })
      if (id === latestRequest.current) setSearch({ status: 'success', result })
    } catch (err: unknown) {
      if (id === latestRequest.current) setSearch({ status: 'error', error: messageOf(err) })
    }
  }

  const presetList = presets.status === 'ready' ? presets.presets : []
  const loading = search.status === 'loading'
  // 検索中は選択を固定し、画面の選択と表示される結果が食い違わないようにする
  const inputsDisabled = presets.status !== 'ready' || loading

  return (
    <div className="app">
      <header className="app-header">
        <h1>ChariRoute</h1>
        <p>大阪市のドコモ・バイクシェアで、徒歩より早く着けるかを概算します</p>
      </header>

      <main>
        <form className="card search-form" onSubmit={onSubmit} noValidate>
          {presets.status === 'error' && (
            <p className="alert alert-error" role="alert">
              地点の一覧を読み込めませんでした。{presets.message}
            </p>
          )}
          <div className="field">
            <label htmlFor="origin">出発地</label>
            <select
              id="origin"
              value={originId}
              onChange={(e) => setOriginId(e.target.value)}
              disabled={inputsDisabled}
            >
              <option value="">
                {presets.status === 'loading' ? '読み込み中…' : '選択してください'}
              </option>
              {presetList.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            className="swap"
            onClick={swap}
            disabled={inputsDisabled}
            aria-label="出発地と目的地を入れ替える"
          >
            ⇅ 入れ替え
          </button>
          <div className="field">
            <label htmlFor="destination">目的地</label>
            <select
              id="destination"
              value={destinationId}
              onChange={(e) => setDestinationId(e.target.value)}
              disabled={inputsDisabled}
            >
              <option value="">
                {presets.status === 'loading' ? '読み込み中…' : '選択してください'}
              </option>
              {presetList.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          {inputError && (
            <p className="alert alert-error" role="alert">
              {inputError}
            </p>
          )}
          <button type="submit" className="primary" disabled={inputsDisabled}>
            {loading ? '検索中…' : '経路を検索'}
          </button>
        </form>

        <SearchResult state={search} />

        <aside className="card caution">
          <h2>ご利用の前に</h2>
          <ul>
            <li>
              所要時間は、地点間の<strong>直線距離</strong>に迂回係数と移動速度を掛けた
              <strong>概算</strong>です。道路に沿った経路ではありません。
            </li>
            <li>
              対象のポート（大阪市内）の判定には未確認の仮定があります。貸出・返却の可否や台数は、
              実際に利用する前に<strong>ドコモ・バイクシェアの公式アプリ</strong>で確認してください。
            </li>
          </ul>
        </aside>
      </main>

    </div>
  )
}

function SearchResult({ state }: { state: SearchState }) {
  switch (state.status) {
    case 'idle':
      return (
        <section className="card muted" aria-live="polite">
          <p>出発地と目的地を選んで「経路を検索」を押してください。</p>
        </section>
      )
    case 'loading':
      return (
        <section className="card muted" aria-live="polite" aria-busy="true">
          <p role="status">ポート情報を取得して経路を計算しています…</p>
        </section>
      )
    case 'error':
      return <ErrorView error={state.error} />
    case 'success':
      return <RouteView result={state.result} />
  }
}

function ErrorView({ error }: { error: ApiError }) {
  const title =
    error.kind === 'gbfs_unavailable'
      ? 'ポート情報を取得できません'
      : error.kind === 'input'
        ? '入力内容を確認してください'
        : error.kind === 'network'
          ? '通信エラー'
          : 'エラーが発生しました'
  return (
    <section className="card alert alert-error" role="alert">
      <h2>{title}</h2>
      <p>{error.message}</p>
      {error.kind === 'gbfs_unavailable' && (
        <p>所要時間の推定にはポートの最新情報が必要なため、結果を表示できません。</p>
      )}
    </section>
  )
}

function RouteView({ result }: { result: RouteResponse }) {
  const { bike_share: bike, walk, recommended, data } = result
  // 比較表と同じく丸めた値どうしの差にする（表示上の数字と食い違わないように）
  const diff = bike ? Math.round(walk.total_minutes) - Math.round(bike.total_minutes) : 0

  return (
    <section className="result" aria-label="検索結果">
      <div className={`card recommend recommend-${recommended}`}>
        <p className="route-names">
          {result.origin.name} → {result.destination.name}
        </p>
        <h2>
          おすすめ：{recommended === 'bike_share' ? 'シェアサイクル' : '徒歩のみ'}
        </h2>
        {recommended === 'bike_share' && bike && (
          <p>
            {diff >= 1
              ? `徒歩のみより 約${diff}分 早く着く見込みです。`
              : '徒歩のみとほぼ同じ所要時間です。'}
          </p>
        )}
        {recommended === 'walk' && bike && (
          <p>この区間では、シェアサイクルを使っても徒歩より早くなりません。</p>
        )}
        {!bike && (
          <p>
            利用できる貸出・返却ポートの組み合わせが見つかりませんでした。徒歩のみの所要時間を表示します。
          </p>
        )}
      </div>

      <div className="card">
        <h2>所要時間の比較（概算）</h2>
        <dl className="compare">
          <div className={recommended === 'bike_share' ? 'best' : undefined}>
            <dt>シェアサイクル</dt>
            <dd>{bike ? `約${formatMinutes(bike.total_minutes)}分` : '利用できません'}</dd>
          </div>
          <div className={recommended === 'walk' ? 'best' : undefined}>
            <dt>徒歩のみ</dt>
            <dd>
              約{formatMinutes(walk.total_minutes)}分
              <small>（直線 {formatDistance(walk.distance_m)}）</small>
            </dd>
          </div>
        </dl>
      </div>

      {bike && <BikeDetail bike={bike} />}

      <div className="card">
        <RouteMap result={result} />
      </div>

      <div className="card data-source">
        <h2>データについて</h2>
        <p>ポート情報の取得時刻：{formatDateTime(data.last_updated)}</p>
        <p>{data.attribution}</p>
        <p>
          ライセンス：
          <a href={data.license_url} target="_blank" rel="noreferrer">
            {data.license}
          </a>
          {' / '}
          <a href={data.dataset_url} target="_blank" rel="noreferrer">
            データセット
          </a>
        </p>
      </div>
    </section>
  )
}

function BikeDetail({ bike }: { bike: BikeShareRoute }) {
  const rows: { label: string; minutes: number; distance?: number }[] = [
    { label: '徒歩（出発地 → 貸出ポート）', minutes: bike.walk_to_rent_minutes, distance: bike.walk_to_rent_m },
    { label: '貸出の手続き', minutes: bike.rent_minutes },
    { label: '自転車（貸出 → 返却ポート）', minutes: bike.bike_minutes, distance: bike.bike_m },
    { label: '返却の手続き', minutes: bike.return_minutes },
    { label: '徒歩（返却ポート → 目的地）', minutes: bike.walk_from_return_minutes, distance: bike.walk_from_return_m },
  ]
  return (
    <>
      <div className="card">
        <h2>シェアサイクルの内訳</h2>
        <table className="breakdown">
          <tbody>
            {rows.map((r) => (
              <tr key={r.label}>
                <th scope="row">
                  {r.label}
                  {r.distance !== undefined && <small>直線 {formatDistance(r.distance)}</small>}
                </th>
                <td>{r.minutes.toFixed(1)}分</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">合計</th>
              <td>{bike.total_minutes.toFixed(1)}分</td>
            </tr>
          </tfoot>
        </table>
      </div>

      <div className="card">
        <h2>利用するポート</h2>
        <ul className="stations">
          <li>
            <span className="tag tag-rent">貸出</span>
            <span className="station-name">{bike.rent_station.name}</span>
            <span className="count">空き自転車 {bike.rent_station.num_bikes_available}台</span>
          </li>
          <li>
            <span className="tag tag-return">返却</span>
            <span className="station-name">{bike.return_station.name}</span>
            <span className="count">空きドック {bike.return_station.num_docks_available}台</span>
          </li>
        </ul>
        <p className="note">台数は取得時刻の時点の値です。</p>
      </div>
    </>
  )
}
