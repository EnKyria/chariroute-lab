// basic-auth.js のテスト（Node 標準の node:test。依存の追加なし）。
// CloudFront の `cloudfront` モジュール（KeyValueStore）は偽物に差し替え、`crypto` は Node のものを使う
// （CloudFront Functions の crypto も createHash('sha256') と digest('hex') を持つ。AWS の公式資料）。
// 実行：node --test infra/cloudfront/basic-auth.test.mjs（scripts/check.py から呼ぶ）
import assert from 'node:assert/strict'
import crypto, { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

// ランタイムが解決する 2 つの import。テストでは取り除き、同じ名前の引数として渡す
const IMPORT_LINES = ["import cf from 'cloudfront';", "import crypto from 'crypto';"]
const source = readFileSync(new URL('./basic-auth.js', import.meta.url), 'utf8')

const USER_PASS = 'tester:correct-horse-battery-staple'
const GOOD = `Basic ${Buffer.from(USER_PASS).toString('base64')}`
const HASH = createHash('sha256').update(GOOD).digest('hex')

/** kvsValue：文字列なら get が返す値、Error なら get が投げる例外。 */
function load(kvsValue) {
  const cf = {
    kvs: () => ({
      get: async (key, opts) => {
        assert.equal(key, 'basic_auth_sha256')
        assert.deepEqual(opts, { format: 'string' })
        if (kvsValue instanceof Error) throw kvsValue
        return kvsValue
      },
    }),
  }
  const body = IMPORT_LINES.reduce((s, line) => s.replace(line, ''), source)
  return new Function('cf', 'crypto', `${body}\nreturn handler;`)(cf, crypto)
}

function event(authorization) {
  const headers = { host: { value: 'example.cloudfront.net' } }
  if (authorization !== undefined) headers.authorization = { value: authorization }
  return { version: '1.0', context: { eventType: 'viewer-request' }, viewer: { ip: '203.0.113.1' },
    request: { method: 'GET', uri: '/api/presets', querystring: {}, headers, cookies: {} } }
}

test('import 文は公式サンプルと同じ 2 行だけで、require と console を使わない', () => {
  for (const line of IMPORT_LINES) assert.equal(source.split(line).length, 2)
  assert.equal(source.match(/^import /gm).length, 2)
  assert.ok(!/require\(/.test(source))
  assert.ok(!/console\./.test(source))
})

test('正しい資格情報なら、Authorization を消してリクエストを先に渡す', async () => {
  const res = await load(HASH)(event(GOOD))
  assert.equal(res.uri, '/api/presets')
  assert.equal(res.headers.authorization, undefined)
  assert.equal(res.headers.host.value, 'example.cloudfront.net')
})

for (const [name, auth] of [
  ['ヘッダーなし', undefined],
  ['空', ''],
  ['パスワード違い', `Basic ${Buffer.from('tester:wrong').toString('base64')}`],
  ['スキームが小文字', GOOD.replace('Basic', 'basic')],
  ['Bearer', `Bearer ${GOOD.slice(6)}`],
  ['末尾に余分な文字', `${GOOD}=`],
  ['ハッシュそのものを送る', `Basic ${HASH}`],
  ['長すぎる', `Basic ${'A'.repeat(2000)}`],
]) {
  test(`401（${name}）：WWW-Authenticate を付け、キャッシュさせない`, async () => {
    const res = await load(HASH)(event(auth))
    assert.equal(res.statusCode, 401)
    assert.match(res.headers['www-authenticate'].value, /^Basic realm="ChariRoute"/)
    assert.equal(res.headers['cache-control'].value, 'no-store')
    assert.equal(res.uri, undefined) // リクエストを先に渡していない
  })
}

for (const [name, value] of [
  ['キーがない（get が例外）', new Error('key not found')],
  ['空の値', ''],
  ['16 進でない', 'x'.repeat(64)],
  ['大文字の 16 進', HASH.toUpperCase()],
  ['短い', HASH.slice(0, 63)],
  ['平文の資格情報を置いた', GOOD],
]) {
  test(`503（KeyValueStore の設定不備：${name}）：正しい資格情報でも通さない`, async () => {
    const res = await load(value)(event(GOOD))
    assert.equal(res.statusCode, 503)
    assert.equal(res.headers['www-authenticate'], undefined)
  })
}
