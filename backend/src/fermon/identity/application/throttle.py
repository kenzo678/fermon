import math
from collections import deque
from datetime import datetime, timedelta

from fermon.identity.application.ports import Clock
from fermon.identity.domain import EMAIL_MAX_LENGTH, TooManyLoginAttemptsError


class LoginThrottle:
    """Failed-login limiter: per account (normalized email) and per client IP.

    A key is blocked while it has ``limit`` failures inside the sliding ``window``; the block
    lifts when the oldest of them leaves the window. A success clears the account's failures
    (never the IP's, or one valid login would erase an attacker's history).

    State is in process memory: it is per worker and lost on restart, which is fine for a single
    API instance. Several instances would each need a shared store (e.g. the database or Redis).
    Memory is bounded: a key keeps at most ``limit`` timestamps, expired keys are dropped, and the
    number of tracked keys is capped (oldest-touched evicted first) so spraying random emails or
    addresses cannot grow it without limit.

    The client IP is whatever the caller passes; behind a reverse proxy that is the proxy's
    address unless the deployment forwards the real one.
    """

    def __init__(
        self,
        clock: Clock,
        *,
        window: timedelta,
        max_account_failures: int = 5,
        max_ip_failures: int = 20,
        max_tracked_keys: int = 10_000,
    ) -> None:
        self._clock = clock
        self._window = window
        self._limits = {"account": max_account_failures, "ip": max_ip_failures}
        self._max_keys = max_tracked_keys
        # insertion order doubles as "least recently touched first"
        self._failures: dict[tuple[str, str], deque[datetime]] = {}

    @property
    def tracked_keys(self) -> int:
        return len(self._failures)

    def check(self, email: str, ip: str | None) -> None:
        """Raises ``TooManyLoginAttemptsError`` when the account or the IP is blocked."""
        now = self._clock()
        waits = [self._wait(key, now) for key in self._keys(email, ip)]
        longest = max(waits)
        if longest > 0:
            raise TooManyLoginAttemptsError(longest)

    def record_failure(self, email: str, ip: str | None) -> None:
        now = self._clock()
        for key in self._keys(email, ip):
            failures = self._failures.pop(key, None)
            if failures is None:
                failures = deque(maxlen=self._limits[key[0]])
            self._drop_expired(failures, now)
            failures.append(now)
            self._failures[key] = failures
        self._bound_memory(now)

    def record_success(self, email: str) -> None:
        self._failures.pop(("account", _account_key(email)), None)

    def _keys(self, email: str, ip: str | None) -> list[tuple[str, str]]:
        keys = [("account", _account_key(email))]
        if ip:
            keys.append(("ip", ip))
        return keys

    def _wait(self, key: tuple[str, str], now: datetime) -> int:
        """Whole seconds until ``key`` may try again; 0 when it is not blocked."""
        failures = self._failures.get(key)
        if failures is None:
            return 0
        self._drop_expired(failures, now)
        if not failures:
            del self._failures[key]
            return 0
        if len(failures) < self._limits[key[0]]:
            return 0
        return max(1, math.ceil((failures[0] + self._window - now).total_seconds()))

    def _drop_expired(self, failures: deque[datetime], now: datetime) -> None:
        while failures and failures[0] + self._window <= now:
            failures.popleft()

    def _bound_memory(self, now: datetime) -> None:
        if len(self._failures) <= self._max_keys:
            return
        for key, failures in list(self._failures.items()):
            self._drop_expired(failures, now)
            if not failures:
                del self._failures[key]
        while len(self._failures) > self._max_keys:
            del self._failures[next(iter(self._failures))]


def _account_key(email: str) -> str:
    return str(email).strip().lower()[:EMAIL_MAX_LENGTH]
