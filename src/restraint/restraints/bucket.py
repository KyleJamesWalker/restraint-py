"""Token bucket rate limiting."""

from __future__ import annotations

from typing import TYPE_CHECKING

from restraint.restraints.base import Reservation, Restraint

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["TokenBucket"]


class TokenBucket(Restraint):
    """Smooth sustained rate with a bounded burst allowance.

    Tokens refill continuously rather than all at once, so there is no window
    boundary to bunch up against. ``Limit(second=3)`` will admit six calls
    across a single second boundary -- three at the end of one window and
    three at the start of the next -- because both are within their window.
    A bucket cannot, which makes it the closer match to how most APIs
    actually meter.

    ``burst`` is how much idle capacity may accumulate, and defaults to one
    interval's worth of tokens:

    ```python
    TokenBucket(rate=5)             # 5/s, at most 5 back to back
    TokenBucket(rate=5, burst=20)   # 5/s sustained, 20 after sitting idle
    TokenBucket(rate=60, per=60.0)  # 60/minute, paced across the minute
    ```

    Capacity is reserved rather than contended for: a caller that arrives
    with the bucket empty is told when its token lands and waits exactly
    that long, so concurrent callers are served in order.

    Args:
        rate: Tokens added per ``per`` seconds.
        per: Length of the refill interval in seconds.
        burst: Maximum tokens that may accumulate. Defaults to ``rate``.
        clock: Monotonic seconds source. Injected by tests.
        sleep: Blocking sleep used by :meth:`gate`. Injected by tests.

    Raises:
        ValueError: ``rate`` or ``per`` is not positive, or ``burst`` is
            less than one.
    """

    def __init__(
        self,
        rate: float,
        *,
        per: float = 1.0,
        burst: float | None = None,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        """Initialise the bucket."""
        super().__init__(clock=clock, sleep=sleep)
        if rate <= 0:
            raise ValueError("rate must be positive")
        if per <= 0:
            raise ValueError("per must be positive")
        capacity = rate if burst is None else burst
        if capacity < 1:
            raise ValueError("burst must be at least 1")
        self.rate = rate
        self.per = per
        self.burst = capacity
        self._per_second = rate / per
        self._tokens = float(capacity)
        self._updated: float | None = None

    @property
    def tokens(self) -> float:
        """Tokens available right now, after accounting for refill."""
        with self._lock:
            self._refill()
            return self._tokens

    def _refill(self) -> None:
        """Add the tokens earned since the last update."""
        now = self._clock()
        if self._updated is None:
            self._updated = now
            return
        elapsed = now - self._updated
        if elapsed <= 0:
            return
        self._updated = now
        self._tokens = min(self.burst, self._tokens + elapsed * self._per_second)

    def _reserve(self) -> Reservation:
        """Take a token, waiting for it to be earned if the bucket is dry."""
        self._refill()
        self._tokens -= 1.0
        if self._tokens >= 0.0:
            return Reservation()
        # Allowed to go negative: the debt is this caller's reserved slot,
        # which is what keeps concurrent callers in arrival order.
        return Reservation(-self._tokens / self._per_second, granted=True)
