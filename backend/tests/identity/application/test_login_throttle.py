from datetime import UTC, datetime, timedelta

import pytest

from fermon.identity.application import LoginThrottle
from fermon.identity.domain import TooManyLoginAttemptsError

T0 = datetime(2026, 1, 1, 12, tzinfo=UTC)
WINDOW = timedelta(minutes=15)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


def make(clock: Clock, **overrides: int) -> LoginThrottle:
    options = {"max_account_failures": 5, "max_ip_failures": 20, "max_tracked_keys": 1000}
    return LoginThrottle(clock, window=WINDOW, **{**options, **overrides})


def fail(throttle: LoginThrottle, times: int, email: str = "a@example.com", ip: str = "1.1.1.1"):
    for _ in range(times):
        throttle.check(email, ip)
        throttle.record_failure(email, ip)


def test_an_account_is_blocked_after_the_configured_number_of_failures() -> None:
    clock = Clock()
    throttle = make(clock)
    fail(throttle, 5)
    with pytest.raises(TooManyLoginAttemptsError) as blocked:
        throttle.check("a@example.com", "2.2.2.2")
    assert blocked.value.retry_after_seconds == 15 * 60
    throttle.check("other@example.com", "2.2.2.2")  # another account is unaffected


def test_the_account_key_ignores_case_and_surrounding_spaces() -> None:
    throttle = make(Clock())
    fail(throttle, 5, email="User@Example.com ")
    with pytest.raises(TooManyLoginAttemptsError):
        throttle.check(" user@example.COM", "9.9.9.9")


def test_retry_after_counts_down_and_the_block_lifts_when_the_window_passes() -> None:
    clock = Clock()
    throttle = make(clock)
    fail(throttle, 5)
    clock.now = T0 + WINDOW - timedelta(seconds=1)
    with pytest.raises(TooManyLoginAttemptsError) as blocked:
        throttle.check("a@example.com", "1.1.1.1")
    assert blocked.value.retry_after_seconds == 1
    clock.now = T0 + WINDOW
    throttle.check("a@example.com", "1.1.1.1")


def test_failures_expire_individually_so_old_ones_stop_counting() -> None:
    clock = Clock()
    throttle = make(clock)
    fail(throttle, 3)
    clock.now = T0 + WINDOW  # the first three are now outside the window
    fail(throttle, 4)
    throttle.check("a@example.com", "1.1.1.1")  # only 4 recent failures
    fail(throttle, 1)
    with pytest.raises(TooManyLoginAttemptsError):
        throttle.check("a@example.com", "1.1.1.1")


def test_success_resets_the_account_counter_but_not_the_ip_counter() -> None:
    throttle = make(Clock(), max_ip_failures=8)
    fail(throttle, 4)
    throttle.record_success("a@example.com")
    fail(throttle, 4)  # account counter restarted: 4 < 5
    throttle.check("a@example.com", "3.3.3.3")
    with pytest.raises(TooManyLoginAttemptsError):
        throttle.check("fresh@example.com", "1.1.1.1")  # 8 failures from the IP


def test_an_ip_is_blocked_across_many_accounts() -> None:
    throttle = make(Clock(), max_ip_failures=4)
    for n in range(4):
        throttle.record_failure(f"user{n}@example.com", "8.8.8.8")
    with pytest.raises(TooManyLoginAttemptsError):
        throttle.check("brand-new@example.com", "8.8.8.8")
    throttle.check("brand-new@example.com", "8.8.4.4")


def test_without_a_client_ip_only_the_account_is_throttled() -> None:
    throttle = make(Clock())
    for _ in range(5):
        throttle.record_failure("a@example.com", None)
    with pytest.raises(TooManyLoginAttemptsError):
        throttle.check("a@example.com", None)


def test_memory_stays_bounded_when_failures_arrive_for_endless_emails() -> None:
    clock = Clock()
    throttle = make(clock, max_tracked_keys=50)
    for n in range(500):
        throttle.record_failure(f"spray{n}@example.com", f"10.0.{n // 250}.{n % 250}")
    assert throttle.tracked_keys <= 50
    clock.now = T0 + WINDOW
    throttle.record_failure("late@example.com", None)
    assert throttle.tracked_keys == 1  # expired entries are pruned, not kept forever
