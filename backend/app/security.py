"""オリジン（API Gateway → Lambda）へのアクセス制限と、API 応答のキャッシュ禁止。plan §7.6。

**ここで行うのは、CloudFront を経由しない直接の呼び出しを止めることだけ。** 利用者本人の認証は
CloudFront Functions の Basic 認証（`infra/cloudfront/basic-auth.js`）が別に行う。

- CloudFront はオリジンへのリクエストに、カスタムヘッダー
  `X-Origin-Verify: <シークレット>` を付ける。
  閲覧者が同じ名前のヘッダーを送っても、CloudFront が値を上書きする（AWS の公式資料）。
- 検証が必要になるのは、次のどちらか：
  - `ORIGIN_VERIFY_SECRET` が設定されている。
  - Lambda 上で動いている（Lambda が自動で設定する `AWS_LAMBDA_FUNCTION_NAME` がある）。
- 検証が必要なのにシークレットが未設定・短すぎるときは、
  **全てのリクエストを 403 にする**（安全側）。
- 比較は hmac.compare_digest（時間差で値を推測されにくくする）。
- シークレットの値とヘッダーの値は、ログにも応答にも出さない。
- 403 は、ルーティング・GBFS・外部 API より前で返す。
"""

import hmac
import json
import logging
import os

from starlette.types import ASGIApp, Message, Receive, Scope, Send

ORIGIN_SECRET_ENV = "ORIGIN_VERIFY_SECRET"
ORIGIN_HEADER = b"x-origin-verify"
MIN_SECRET_LEN = 32
LAMBDA_ENV = "AWS_LAMBDA_FUNCTION_NAME"

logger = logging.getLogger("chariroute")

FORBIDDEN_BODY = {"detail": "アクセスが許可されていません", "code": "forbidden"}
# API の応答には座標・地点名・検索語が入りうるので、CloudFront・ブラウザ・中継でキャッシュさせない
NO_STORE = "no-store"


def _origin_check() -> tuple[bool, str | None]:
    """(検証が必要か, 有効なシークレット)。必要なのに有効なシークレットがなければ (True, None)。

    前後の空白は取り除いてから長さを数える（空白だけの値をシークレットとして使わせない）。
    """
    raw = os.environ.get(ORIGIN_SECRET_ENV, "")
    secret = raw.strip()
    required = bool(raw) or bool(os.environ.get(LAMBDA_ENV))
    if not required:
        return False, None
    if len(secret) < MIN_SECRET_LEN:
        return True, None
    return True, secret


def origin_allowed(headers: list[tuple[bytes, bytes]]) -> bool:
    """ASGI の生のヘッダー（名前は小文字）で判定する。"""
    required, secret = _origin_check()
    if not required:
        return True
    if secret is None:
        # 値は出さない（長さも出さない）
        logger.error("%s が未設定か、%d 文字未満です。全てのリクエストを拒否します",
                     ORIGIN_SECRET_ENV, MIN_SECRET_LEN)
        return False
    given = next((v for k, v in headers if k.lower() == ORIGIN_HEADER), b"")
    return hmac.compare_digest(given, secret.encode("utf-8"))


class OriginAndCacheMiddleware:
    """純粋な ASGI ミドルウェア。

    - 共有シークレットが合わなければ、アプリに渡さずに 403 を返す。
    - アプリの応答の開始（http.response.start）に Cache-Control: no-store を付ける。
    BaseHTTPMiddleware の call_next を使わないので、ストリーミングや例外の扱いが変わらない。
    未処理の例外による 500 は、外側の ServerErrorMiddleware が返すのでここを通らない
    （main.py の例外ハンドラで no-store を付ける）。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if not origin_allowed(scope.get("headers", [])):
            body = json.dumps(FORBIDDEN_BODY, ensure_ascii=False).encode("utf-8")
            await send({"type": "http.response.start", "status": 403, "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
                (b"cache-control", NO_STORE.encode("ascii"))]})
            await send({"type": "http.response.body", "body": body})
            return

        async def send_no_store(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", [])
                           if k.lower() != b"cache-control"]
                headers.append((b"cache-control", NO_STORE.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_no_store)
