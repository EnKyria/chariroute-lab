// 現在地の取得（ブラウザの Geolocation API）。ユーザーがボタンを押したときだけ呼ぶ。
// 取得した座標はログや保存領域に出さない。

export type GeoErrorKind = 'insecure' | 'unsupported' | 'denied' | 'timeout' | 'unavailable'

export class GeoError extends Error {
  readonly kind: GeoErrorKind
  constructor(kind: GeoErrorKind) {
    super(GEO_MESSAGES[kind])
    this.kind = kind
    this.name = 'GeoError'
  }
}

export const GEO_MESSAGES: Record<GeoErrorKind, string> = {
  insecure:
    '現在地は HTTPS（または localhost）で開いたページでだけ取得できます。地図のタップか地点検索で指定してください',
  unsupported: 'このブラウザは現在地の取得に対応していません',
  denied: '現在地の利用が許可されていません。ブラウザの設定で位置情報を許可してください',
  timeout: '現在地の取得がタイムアウトしました。電波の良い場所で再度お試しください',
  unavailable: '現在地を取得できませんでした。しばらくしてから再度お試しください',
}

export const GEO_TIMEOUT_MS = 10_000

export function getCurrentPosition(): Promise<{ lat: number; lon: number }> {
  return new Promise((resolve, reject) => {
    if (typeof window !== 'undefined' && window.isSecureContext === false) {
      reject(new GeoError('insecure'))
      return
    }
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      reject(new GeoError('unsupported'))
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
      (err) => {
        // 1: PERMISSION_DENIED、2: POSITION_UNAVAILABLE、3: TIMEOUT
        if (err.code === 1) reject(new GeoError('denied'))
        else if (err.code === 3) reject(new GeoError('timeout'))
        else reject(new GeoError('unavailable'))
      },
      { enableHighAccuracy: true, timeout: GEO_TIMEOUT_MS, maximumAge: 30_000 },
    )
  })
}
