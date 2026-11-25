"""外部送信の共通部分（リミッター・ヘッダー・URL の設定）のテスト。

ID は evaluator の設計（OB-*）。
"""

import threading
import time

import pytest
from fakes import ManualClock

from app.outbound import (
    DEFAULT_USER_AGENT,
    MIN_INTERVAL_SECONDS,
    OutboundError,
    RateLimiter,
    https_url,
    outbound_headers,
)


def limiter(clock: ManualClock) -> RateLimiter:
    return RateLimiter(clock=clock, sleep=clock.sleep)


def test_ob1_waits_before_first_request():
    clock = ManualClock()
    lim = limiter(clock)
    assert lim.run(lambda: "ok") == "ok"
    assert clock.sleeps == [pytest.approx(MIN_INTERVAL_SECONDS)]
    assert MIN_INTERVAL_SECONDS >= 1.1


def test_ob2_waits_for_the_rest_of_the_interval():
    clock = ManualClock()
    lim = limiter(clock)
    lim.run(lambda: None)
    clock.now += 0.3
    lim.run(lambda: None)
    assert clock.sleeps[1] == pytest.approx(0.8)


def test_ob3_no_wait_after_interval():
    clock = ManualClock()
    lim = limiter(clock)
    lim.run(lambda: None)
    clock.now += 1.5
    lim.run(lambda: None)
    assert len(clock.sleeps) == 1


def test_ob2b_interval_is_measured_from_send_time_not_response_time():
    """送信の時刻から次の送信までを 1.1 秒以上空ける（応答に時間がかかっても短くしない）。"""
    clock = ManualClock()
    lim = limiter(clock)
    sent: list[float] = []

    def send() -> None:
        sent.append(clock.now)
        clock.now += 0.5  # 応答まで 0.5 秒

    for _ in range(3):
        lim.run(send)
    gaps = [b - a for a, b in zip(sent, sent[1:], strict=False)]
    assert all(g >= MIN_INTERVAL_SECONDS - 1e-9 for g in gaps)


def test_ob4_requests_are_serialized_across_threads():
    """ロックを応答の受信まで保持するので、同時に 2 つの送信は起きない（実時間、間隔は短縮）。"""
    lim = RateLimiter(interval=0.01)
    active, peak = 0, 0
    guard = threading.Lock()

    def send() -> None:
        nonlocal active, peak
        with guard:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02)
        with guard:
            active -= 1

    threads = [threading.Thread(target=lim.run, args=(send,)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak == 1
    assert lim.sent == 4


def test_ob2c_early_return_from_sleep_is_compensated():
    """sleep が早く戻っても（Windows で実測）、時計で確かめて 1.1 秒に届くまで待ち直す。"""
    clock = ManualClock()

    def short_sleep(seconds: float) -> None:
        clock.sleeps.append(seconds)
        clock.now += seconds * 0.9  # 要求より 1 割短くしか眠らない

    lim = RateLimiter(clock=clock, sleep=short_sleep)
    sent: list[float] = []
    for _ in range(3):
        lim.run(lambda: sent.append(clock.now))
    assert sent[0] - 1000.0 >= MIN_INTERVAL_SECONDS
    assert all(b - a >= MIN_INTERVAL_SECONDS for a, b in zip(sent, sent[1:], strict=False))


def test_ob5_lock_released_after_exception_and_interval_kept():
    clock = ManualClock()
    lim = limiter(clock)

    def boom() -> None:
        raise OutboundError("down")

    with pytest.raises(OutboundError):
        lim.run(boom)
    assert lim.run(lambda: "second") == "second"
    assert clock.sleeps[1] == pytest.approx(MIN_INTERVAL_SECONDS)


def test_ob6_no_retry_on_failure():
    clock = ManualClock()
    lim = limiter(clock)
    calls = 0

    def fail() -> None:
        nonlocal calls
        calls += 1
        raise OutboundError("timeout")

    with pytest.raises(OutboundError):
        lim.run(fail)
    assert calls == 1 and lim.sent == 1


def test_deadline_prevents_sending():
    clock = ManualClock()
    lim = limiter(clock)
    called = False

    def send() -> None:
        nonlocal called
        called = True

    with pytest.raises(OutboundError):
        lim.run(send, deadline=clock.now + 0.5)  # 最初の待機 1.1 秒で締め切りを超える
    assert not called and lim.sent == 0


def test_ob9_default_headers(monkeypatch):
    monkeypatch.delenv("OUTBOUND_USER_AGENT", raising=False)
    monkeypatch.delenv("OUTBOUND_REFERER", raising=False)
    h = outbound_headers()
    assert h["User-Agent"] == DEFAULT_USER_AGENT
    assert h["User-Agent"].startswith("ChariRoute/")
    assert "@" not in h["User-Agent"]
    assert "Referer" not in h


def test_ob10_referer_and_user_agent_from_env(monkeypatch):
    monkeypatch.setenv("OUTBOUND_REFERER", "https://chariroute.example/")
    monkeypatch.setenv("OUTBOUND_USER_AGENT", "ChariRoute/9.9 (+test)")
    h = outbound_headers()
    assert h["Referer"] == "https://chariroute.example/"
    assert h["User-Agent"] == "ChariRoute/9.9 (+test)"


def test_ob11_only_https_urls():
    assert https_url(None, "https://a.test/x/", "X") == "https://a.test/x"
    assert https_url("https://b.test", "https://a.test", "X") == "https://b.test"
    for bad in ("http://a.test", "file:///etc/passwd", "ftp://a"):
        with pytest.raises(ValueError):
            https_url(bad, "https://a.test", "X")
