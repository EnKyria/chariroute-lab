"""外部の公開サービス（FOSSGIS OSRM・Nominatim）への送信の共通部分。

利用条件（CLAUDE.md、docs/engineering-notes.md §9.5）を守るための仕組みをここに集める：
- サービスごとに 1 つ、プロセス全体で共有するリミッター（RateLimiter）。
  - ロックを送信から応答の受信まで保持する（同時の接続は 1 つ）。
  - 前回の送信から MIN_INTERVAL_SECONDS 経っていなければ待つ。プロセスで最初の送信の前にも待つ。
  - 自動リトライはしない。
- アプリを識別できる User-Agent と、設定されていれば Referer を付ける。
- URL は環境変数で切り替えられる（https:// のみ）。

ログやエラーメッセージに URL を入れない（経路の URL には座標が、検索の URL には検索語が入るため）。
"""

import http.client
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

MIN_INTERVAL_SECONDS = 1.1
REQUEST_TIMEOUT_SECONDS = 4.0
# OSRM の Table（とくに routed-bike の 11×11）は、実測で約 9.7 秒かかった
# （2026-11-25 のスモークテスト）
TABLE_TIMEOUT_SECONDS = 15.0
DEFAULT_USER_AGENT = "ChariRoute/0.1 (+https://github.com/EnKyria/chariroute-lab)"
DEFAULT_OSRM_FOOT_URL = "https://routing.openstreetmap.de/routed-foot"
DEFAULT_OSRM_BIKE_URL = "https://routing.openstreetmap.de/routed-bike"
DEFAULT_NOMINATIM_URL = "https://nominatim.openstreetmap.org"


EXTERNAL_APIS_ENV = "EXTERNAL_APIS_ENABLED"


def external_apis_enabled() -> bool:
    """FOSSGIS OSRM・Nominatim への送信を許可するか（plan §7.3）。

    既定は無効。環境変数が厳密に "true" のときだけ有効にする
    （大文字・小文字と前後の空白は問わない）。
    未設定・空・"1"・"yes"・綴りの誤りなどは、すべて無効として扱う（安全側に倒す）。
    送信のたびに読むので、テストや設定の変更がすぐに反映される。
    ODPT の GBFS は対象外（本番でも取得する）。
    """
    return os.environ.get(EXTERNAL_APIS_ENV, "").strip().lower() == "true"


class OutboundError(Exception):
    """外部サービスへの送信に失敗した。メッセージに URL・座標・検索語を入れない。"""

    def __init__(self, message: str, *, busy: bool = False) -> None:
        super().__init__(message)
        self.busy = busy  # 混雑（429 など）なら True


@dataclass(frozen=True)
class HttpResult:
    status: int
    body: Any  # JSON として解釈した本文（解釈できなければ None）


def https_url(value: str | None, default: str, name: str) -> str:
    url = (value or default).rstrip("/")
    if not url.startswith("https://"):
        raise ValueError(f"{name} は https:// で始まる必要があります")
    return url


def outbound_headers() -> dict[str, str]:
    headers = {
        "User-Agent": os.environ.get("OUTBOUND_USER_AGENT") or DEFAULT_USER_AGENT,
        "Accept": "application/json",
    }
    referer = os.environ.get("OUTBOUND_REFERER")
    if referer:
        headers["Referer"] = referer
    return headers


def http_get_json(url: str, timeout: float, headers: dict[str, str]) -> HttpResult:
    """GET して JSON を返す。4xx/5xx も本文ごと返す（OSRM は 400 の本文に code を入れるため）。

    通信そのものの失敗だけを OutboundError にする。リトライはしない。
    """
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            status, raw = res.status, res.read()
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            raw = e.read()
        except (OSError, http.client.HTTPException):
            raw = b""
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as e:
        raise OutboundError(f"通信エラー（{type(e).__name__}）") from e
    try:
        body = json.loads(raw) if raw else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        body = None
    return HttpResult(status, body)


Fetcher = Callable[[str, float, dict[str, str]], HttpResult]


class RateLimiter:
    """1 つのサービスへの送信を直列にし、送信の間隔を MIN_INTERVAL_SECONDS 以上にする。

    プロセス全体で共有する（サービスごとに 1 つ）。時計と sleep は差し替えられる（テスト用）。
    """

    def __init__(self, interval: float = MIN_INTERVAL_SECONDS,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.interval = interval
        self.clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last_sent: float | None = None
        self.sent = 0  # 送信した回数（評価・テスト用）

    def run[T](self, send: Callable[[], T], deadline: float | None = None) -> T:
        """待ってから send を 1 回だけ呼ぶ。ロックは send が戻るまで保持する。

        deadline（clock の値）までに送信できないなら、送らずに OutboundError にする。
        """
        with self._lock:
            now = self.clock()
            # 最初の送信の前にも待つ（実行環境が入れ替わった直後の間隔を保証するため）
            wait = self.interval if self._last_sent is None else (
                self._last_sent + self.interval - now)
            if deadline is not None and now + max(wait, 0.0) >= deadline:
                raise OutboundError("検索全体の制限時間を超えました")
            target = now + max(wait, 0.0)
            # sleep が早く戻ることがある（Windows で実測 1.09 秒）ので、時計で確かめて待ち直す
            while (remaining := target - self.clock()) > 0:
                self._sleep(remaining)
            self._last_sent = self.clock()
            self.sent += 1
            return send()


def query(params: dict[str, str]) -> str:
    return urllib.parse.urlencode(params, safe=",;")
