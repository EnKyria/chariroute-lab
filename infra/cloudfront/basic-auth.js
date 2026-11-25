// CloudFront Functions（ランタイム cloudfront-js-2.0、イベント viewer-request）の Basic 認証。plan §7.6 の (2)。
// 画面（S3）と API（/api/*）の全てのビヘイビアに関連付ける。
//
// - 資格情報そのものは、ここにもリポジトリにも置かない。
//   関連付けた KeyValueStore のキー `basic_auth_sha256` に、
//   "Basic <base64(ユーザー名:パスワード)>" の SHA-256（小文字の 16 進 64 文字）だけを置く（docs/deploy.md）。
// - KeyValueStore を読めない・値の形式が不正なときは、通さずに 503 を返す（安全側）。
// - 認証に成功したら Authorization ヘッダーを消してから先に渡す（オリジンに資格情報を届けない）。
// - HTTPS の強制は、ビヘイビアの Viewer protocol policy を https-only にして行う
//   （関数のイベントには、閲覧者のプロトコルを表す項目がない）。
// - ログ出力の関数は使わない（資格情報を CloudWatch に残さないため）。
// import の書き方は、AWS の公式サンプル（トークンの検証。KeyValueStore と crypto を使う）に合わせた
import cf from 'cloudfront';
import crypto from 'crypto';

const kvs = cf.kvs();
const KEY = 'basic_auth_sha256';
const NO_STORE = { value: 'no-store' };

function unauthorized() {
  return {
    statusCode: 401,
    statusDescription: 'Unauthorized',
    headers: {
      'www-authenticate': { value: 'Basic realm="ChariRoute", charset="UTF-8"' },
      'cache-control': NO_STORE,
    },
  };
}

function unavailable() {
  return { statusCode: 503, statusDescription: 'Service Unavailable', headers: { 'cache-control': NO_STORE } };
}

// 長さが同じ 16 進の文字列を、途中で打ち切らずに比べる
function sameHex(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function handler(event) {
  const request = event.request;
  let expected;
  try {
    expected = await kvs.get(KEY, { format: 'string' });
  } catch (e) {
    return unavailable(); // キーがない・読めない
  }
  if (typeof expected !== 'string' || !/^[0-9a-f]{64}$/.test(expected)) return unavailable();

  const header = request.headers.authorization;
  const given = header && typeof header.value === 'string' ? header.value : '';
  if (given.slice(0, 6) !== 'Basic ' || given.length > 1024) return unauthorized();
  const digest = crypto.createHash('sha256').update(given).digest('hex');
  if (!sameHex(digest, expected)) return unauthorized();

  delete request.headers.authorization;
  return request;
}
