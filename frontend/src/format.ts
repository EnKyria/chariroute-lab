/** 合計や差分の表示用（整数の分）。 */
export function formatMinutes(minutes: number): string {
  return String(Math.max(0, Math.round(minutes)))
}

export function formatDistance(meters: number): string {
  return meters >= 1000 ? `${(meters / 1000).toFixed(1)}km` : `${Math.round(meters)}m`
}

const DATE_TIME = new Intl.DateTimeFormat('ja-JP', {
  timeZone: 'Asia/Tokyo',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
})

/** ISO 8601 の日時を日本時間で表示する。解釈できなければ元の文字列をそのまま出す。 */
export function formatDateTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : `${DATE_TIME.format(d)}（日本時間）`
}
