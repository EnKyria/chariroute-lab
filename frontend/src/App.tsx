import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError, fetchPresets, searchPlaces, searchRoute } from './api/client'
import type { BikeShareRoute, PlaceCandidate, Preset, RouteResponse } from './api/types'
import { formatDateTime, formatDistance, formatMinutes } from './format'
import { GeoError, getCurrentPosition } from './geolocation'
import { inOsaka, samePoint, SOURCE_LABEL, toLocation, type SelectedPoint } from './points'
import RouteMap, { type PickTarget } from './RouteMap'

const CONTACT_EMAIL = 'chariroute.dev@gmail.com'
const REPO_URL = 'https://github.com/EnKyria/chariroute-lab'
const FIXTHEMAP_URL = 'https://www.openstreetmap.org/fixthemap'
const OUTSIDE_AREA = '大阪市の周辺の地点を指定してください'

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

const TARGET_LABEL: Record<PickTarget, string> = { origin: '出発地', destination: '目的地' }

export default function App() {
  const [presets, setPresets] = useState<PresetsState>({ status: 'loading' })
  const [origin, setOrigin] = useState<SelectedPoint | null>(null)
  const [destination, setDestination] = useState<SelectedPoint | null>(null)
  const [pickTarget, setPickTarget] = useState<PickTarget | null>(null)
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

  const loading = search.status === 'loading'

  function setPoint(target: PickTarget, p: SelectedPoint | null) {
    if (target === 'origin') setOrigin(p)
    else setDestination(p)
    setInputError(null)
    // 地点を変えたら、古い結果（別の地点の経路）を残さない
    latestRequest.current++
    setSearch({ status: 'idle' })
  }

  function onPick(target: PickTarget, lat: number, lon: number) {
    setPickTarget(null)
    if (!inOsaka(lat, lon)) {
      setInputError(OUTSIDE_AREA)
      return
    }
    setPoint(target, { source: 'map', name: '地図で選んだ地点', lat, lon })
  }

  function swap() {
    setOrigin(destination)
    setDestination(origin)
    setInputError(null)
    latestRequest.current++
    setSearch({ status: 'idle' })
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!origin || !destination) {
      setInputError('出発地と目的地を指定してください')
      return
    }
    if (samePoint(origin, destination)) {
      setInputError('出発地と目的地に別の地点を指定してください')
      return
    }
    setInputError(null)
    setPickTarget(null)
    const id = ++latestRequest.current
    setSearch({ status: 'loading' })
    try {
      const result = await searchRoute({
        origin: toLocation(origin),
        destination: toLocation(destination),
      })
      if (id === latestRequest.current) setSearch({ status: 'success', result })
    } catch (err: unknown) {
      if (id === latestRequest.current) setSearch({ status: 'error', error: messageOf(err) })
    }
  }

  const bike = search.status === 'success' ? search.result.bike_share : null

  return (
    <div className="app">
      <header className="app-header">
        <h1>ChariRoute</h1>
        <p>
          大阪市のドコモ・バイクシェアで、推定所要時間が最小になる貸出ポートと返却ポートの組み合わせを探します
        </p>
      </header>

      <main>
        <form className="card search-form" onSubmit={onSubmit} noValidate>
          {presets.status === 'error' && (
            <p className="alert alert-error" role="alert">
              プリセットの一覧を読み込めませんでした。{presets.message}
            </p>
          )}
          <PointPicker
            target="origin"
            point={origin}
            presets={presets}
            disabled={loading}
            picking={pickTarget === 'origin'}
            onChange={(p) => setPoint('origin', p)}
            onTogglePick={() => setPickTarget(pickTarget === 'origin' ? null : 'origin')}
          />
          <button
            type="button"
            className="swap"
            onClick={swap}
            disabled={loading}
            aria-label="出発地と目的地を入れ替える"
          >
            ⇅ 入れ替え
          </button>
          <PointPicker
            target="destination"
            point={destination}
            presets={presets}
            disabled={loading}
            picking={pickTarget === 'destination'}
            onChange={(p) => setPoint('destination', p)}
            onTogglePick={() => setPickTarget(pickTarget === 'destination' ? null : 'destination')}
          />
          {inputError && (
            <p className="alert alert-error" role="alert">
              {inputError}
            </p>
          )}
          <p className="notice">
            経路計算のため、出発地・目的地の座標を外部サービス（FOSSGIS の OSRM、ドイツ）に送信します。
            送信した内容は、FOSSGIS のサーバーログに記録されます。
          </p>
          <button type="submit" className="primary" disabled={loading}>
            {loading ? '検索中…' : '経路を検索'}
          </button>
        </form>

        <div className="card">
          <RouteMap
            origin={origin}
            destination={destination}
            bike={bike}
            pickTarget={pickTarget}
            onPick={onPick}
          />
        </div>

        <SearchResult state={search} />

        <aside className="card caution">
          <h2>ご利用の前に</h2>
          <ul>
            <li>
              所要時間は、道路距離と一定の速度（徒歩 4.8 km/h・自転車 15 km/h）から求めた
              <strong>推定値</strong>です（実測ではありません）。貸出・返却の手続きに各 1 分を加えています。
            </li>
            <li>
              ポートの候補は直線距離で絞り込んでいます（貸出・返却とも最大 11 か所）。結果は候補の中で最小のもので、
              <strong>全てのポートの組み合わせの中での最適解は保証しません</strong>。
            </li>
            <li>
              対象のポート（大阪市内）の判定には未確認の仮定があります。貸出・返却の可否や台数は、
              実際に利用する前に<strong>ドコモ・バイクシェアの公式アプリ</strong>で確認してください。
            </li>
          </ul>
        </aside>
      </main>

      <Footer />
    </div>
  )
}

// --- 地点の指定 --------------------------------------------------------------------
interface PickerProps {
  target: PickTarget
  point: SelectedPoint | null
  presets: PresetsState
  disabled: boolean
  picking: boolean
  onChange: (p: SelectedPoint | null) => void
  onTogglePick: () => void
}

function PointPicker({ target, point, presets, disabled, picking, onChange, onTogglePick }: PickerProps) {
  const label = TARGET_LABEL[target]
  const [gpsState, setGpsState] = useState<{ loading: boolean; error: string | null }>({
    loading: false,
    error: null,
  })
  const [searchOpen, setSearchOpen] = useState(false)
  // 取得中に地点が変わったり検索が始まったりしたら、遅れて届いた現在地で上書きしない
  const gpsToken = useRef(0)
  useEffect(() => {
    gpsToken.current++
  }, [point, disabled])
  const presetList = presets.status === 'ready' ? presets.presets : []
  const presetValue = point?.source === 'preset' ? (point.presetId ?? '') : ''

  function onPreset(id: string) {
    const p = presetList.find((x) => x.id === id)
    onChange(p ? { source: 'preset', presetId: p.id, name: p.name, lat: p.lat, lon: p.lon } : null)
  }

  async function onGps() {
    const token = ++gpsToken.current
    setGpsState({ loading: true, error: null })
    try {
      const pos = await getCurrentPosition()
      if (token !== gpsToken.current) {
        setGpsState({ loading: false, error: null })
        return
      }
      if (!inOsaka(pos.lat, pos.lon)) {
        setGpsState({ loading: false, error: `現在地は対象エリアの外です。${OUTSIDE_AREA}` })
        return
      }
      setGpsState({ loading: false, error: null })
      onChange({ source: 'gps', name: '現在地', lat: pos.lat, lon: pos.lon })
    } catch (e: unknown) {
      const message =
        e instanceof GeoError ? e.message : '現在地を取得できませんでした。しばらくしてから再度お試しください'
      setGpsState({ loading: false, error: message })
    }
  }

  return (
    <fieldset className="picker" disabled={disabled}>
      <legend>{label}</legend>
      <p className="picked" aria-live="polite" data-testid={`${target}-picked`}>
        {point ? (
          <>
            <span className="tag tag-source">{SOURCE_LABEL[point.source]}</span>
            {point.name}
          </>
        ) : (
          <span className="muted">未指定</span>
        )}
      </p>
      <div className="field">
        <label htmlFor={`${target}-preset`}>{label}のプリセット</label>
        <select
          id={`${target}-preset`}
          value={presetValue}
          onChange={(e) => onPreset(e.target.value)}
          disabled={presets.status !== 'ready'}
        >
          <option value="">{presets.status === 'loading' ? '読み込み中…' : '選択してください'}</option>
          {presetList.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>
      <div className="picker-actions">
        <button type="button" onClick={onGps} disabled={gpsState.loading}>
          {gpsState.loading ? '取得中…' : '現在地'}
        </button>
        <button type="button" onClick={onTogglePick} aria-pressed={picking}>
          {picking ? 'タップ待ち（取消）' : '地図で選ぶ'}
        </button>
        <button type="button" onClick={() => setSearchOpen(!searchOpen)} aria-expanded={searchOpen}>
          地点検索
        </button>
      </div>
      {gpsState.error && (
        <p className="alert alert-error" role="alert">
          {gpsState.error}
        </p>
      )}
      {searchOpen && (
        <PlaceSearch
          target={target}
          onSelect={(c) => {
            onChange({ source: 'place', name: c.name, lat: c.lat, lon: c.lon })
            setSearchOpen(false)
          }}
        />
      )}
    </fieldset>
  )
}

type PlaceSearchState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'done'; places: PlaceCandidate[] }
  | { status: 'error'; error: ApiError }

/** 地点検索。検索ボタンを押したときだけ送信する（オートコンプリートはしない）。 */
function PlaceSearch({ target, onSelect }: { target: PickTarget; onSelect: (c: PlaceCandidate) => void }) {
  const [q, setQ] = useState('')
  const [state, setState] = useState<PlaceSearchState>({ status: 'idle' })
  const [error, setError] = useState<string | null>(null)
  const id = `${target}-place-q`

  async function run() {
    const query = q.trim()
    if (query.length < 2 || query.length > 64) {
      setError('検索語は 2〜64 文字で入力してください')
      return
    }
    setError(null)
    setState({ status: 'loading' })
    try {
      const res = await searchPlaces({ q: query })
      setState({ status: 'done', places: res.places })
    } catch (e: unknown) {
      setState({ status: 'error', error: messageOf(e) })
    }
  }

  return (
    <div className="place-search">
      <label htmlFor={id}>{TARGET_LABEL[target]}を検索（駅名・施設名）</label>
      <p className="note">
        駅名・施設名で検索してください。個人名・住所・電話番号などは入力しないでください。
        検索語は Nominatim（OpenStreetMap）に送信され、そのサーバーログに記録されることがあります。
      </p>
      <div className="place-row">
        <input
          id={id}
          type="search"
          value={q}
          maxLength={64}
          autoComplete="off"
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              if (state.status !== 'loading') void run()
            }
          }}
        />
        <button type="button" onClick={() => void run()} disabled={state.status === 'loading'}>
          {state.status === 'loading' ? '検索中…' : '検索'}
        </button>
      </div>
      {error && (
        <p className="alert alert-error" role="alert">
          {error}
        </p>
      )}
      {state.status === 'error' && (
        <p className="alert alert-error" role="alert">
          {state.error.message}
        </p>
      )}
      {state.status === 'done' &&
        (state.places.length === 0 ? (
          <p className="note">見つかりませんでした。別の駅名・施設名でお試しください。</p>
        ) : (
          <ul className="place-results" aria-label={`${TARGET_LABEL[target]}の検索結果`}>
            {state.places.map((c) => (
              <li key={`${c.lat},${c.lon},${c.label}`}>
                <button type="button" onClick={() => onSelect(c)}>
                  <strong>{c.name}</strong>
                  <small>{c.label}</small>
                </button>
              </li>
            ))}
          </ul>
        ))}
    </div>
  )
}

// --- 検索結果 ----------------------------------------------------------------------
function SearchResult({ state }: { state: SearchState }) {
  switch (state.status) {
    case 'idle':
      return (
        <section className="card muted" aria-live="polite">
          <p>出発地と目的地を指定して「経路を検索」を押してください。</p>
        </section>
      )
    case 'loading':
      return (
        <section className="card muted" aria-live="polite" aria-busy="true">
          <p role="status">ポート情報を取得し、道路に沿った経路を計算しています…（最大 30 秒ほどかかることがあります）</p>
        </section>
      )
    case 'error':
      return <ErrorView error={state.error} />
    case 'success':
      return <RouteView result={state.result} />
  }
}

const ERROR_TITLE: Record<ApiError['kind'], string> = {
  gbfs_unavailable: 'ポート情報を取得できません',
  route_unavailable: '道路の経路を取得できません',
  places_unavailable: '地点を検索できません',
  busy: '混雑しています',
  input: '入力内容を確認してください',
  network: '通信エラー',
  server: 'エラーが発生しました',
  invalid_response: 'エラーが発生しました',
}

function ErrorView({ error }: { error: ApiError }) {
  return (
    <section className="card alert alert-error" role="alert">
      <h2>{ERROR_TITLE[error.kind]}</h2>
      <p>{error.message}</p>
      {(error.kind === 'gbfs_unavailable' || error.kind === 'route_unavailable') && (
        <p>推定所要時間の計算に必要な情報を取得できなかったため、結果を表示できません。</p>
      )}
    </section>
  )
}

function RouteView({ result }: { result: RouteResponse }) {
  const { bike_share: bike, data } = result
  return (
    <section className="result" aria-label="検索結果">
      <div className={`card summary${bike ? ' summary-found' : ''}`}>
        <p className="route-names">
          {result.origin.name} → {result.destination.name}
        </p>
        {bike ? (
          <>
            <h2>推定所要時間 約{formatMinutes(bike.total_minutes)}分</h2>
            <p>
              {bike.rent_station.name} で借りて、{bike.return_station.name} に返す組み合わせです。
            </p>
          </>
        ) : (
          <>
            <h2>利用できるシェアサイクルの経路が見つかりませんでした</h2>
            <p>
              貸出・返却できるポートの組み合わせがないか、道路でつながる組み合わせがありませんでした。
            </p>
          </>
        )}
      </div>
      {bike && <BikeDetail bike={bike} />}
      <DataSourceView data={data} />
    </section>
  )
}

const LEG_LABEL = ['徒歩（出発地 → 貸出ポート）', '自転車（貸出 → 返却ポート）', '徒歩（返却ポート → 目的地）']

function BikeDetail({ bike }: { bike: BikeShareRoute }) {
  const [walk1, ride, walk2] = bike.legs
  const rows: { label: string; minutes: number; distance?: number }[] = []
  if (walk1) rows.push({ label: LEG_LABEL[0] ?? '', minutes: walk1.minutes, distance: walk1.distance_m })
  rows.push({ label: '貸出の手続き', minutes: bike.rent_minutes })
  if (ride) rows.push({ label: LEG_LABEL[1] ?? '', minutes: ride.minutes, distance: ride.distance_m })
  rows.push({ label: '返却の手続き', minutes: bike.return_minutes })
  if (walk2) rows.push({ label: LEG_LABEL[2] ?? '', minutes: walk2.minutes, distance: walk2.distance_m })
  return (
    <>
      <div className="card">
        <h2>区間ごとの距離と推定所要時間</h2>
        <table className="breakdown">
          <tbody>
            {rows.map((r) => (
              <tr key={r.label}>
                <th scope="row">
                  {r.label}
                  {r.distance !== undefined && <small>道路距離 {formatDistance(r.distance)}</small>}
                </th>
                <td>{r.minutes.toFixed(1)}分</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">合計（推定）</th>
              <td>{bike.total_minutes.toFixed(1)}分</td>
            </tr>
          </tfoot>
        </table>
        <p className="note">
          所要時間は、道路距離と一定の速度から求めた推定値です（実測ではありません）。
        </p>
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

function DataSourceView({ data }: { data: RouteResponse['data'] }) {
  return (
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
      <p>
        経路：
        <a href={data.routing.provider_url} target="_blank" rel="noreferrer">
          {data.routing.provider}
        </a>
        {' / 地図データ：'}
        <a href={data.routing.map_data_url} target="_blank" rel="noreferrer">
          {data.routing.map_data}
        </a>
      </p>
      <p>
        <a href={data.routing.fixthemap_url} target="_blank" rel="noreferrer">
          地図の誤りを報告（OpenStreetMap）
        </a>
      </p>
    </div>
  )
}

function Footer() {
  return (
    <footer className="app-footer">
      <p>
        経路：OSRM / FOSSGIS（routing.openstreetmap.de） ・ 地点検索：Nominatim / OpenStreetMap ・ 地図：©{' '}
        <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">
          OpenStreetMap
        </a>{' '}
        contributors ・ ポート情報：ドコモ・バイクシェア / ODPT（CC BY 4.0）
      </p>
      <p>
        <a href={FIXTHEMAP_URL} target="_blank" rel="noreferrer">
          地図の誤りを報告
        </a>
        {' ・ '}
        <a href={REPO_URL} target="_blank" rel="noreferrer">
          ソースコード（GitHub）
        </a>
      </p>
      <p>
        運営者の連絡先：<a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
      </p>
      <p>個人の学習用の非商用サービスです。</p>
    </footer>
  )
}
