"""Exponential backoff driven by call outcomes."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from restraint.restraints.base import Reservation, Restraint

if TYPE_CHECKING:
    from collections.abc import Callable

    from restraint.outcome import Outcome

__all__ = ["Backoff"]


class Backoff(Restraint):
    """Hold calls back after failures, easing off again once they succeed.

    Every other restraint here paces calls on a schedule fixed in advance.
    This one reacts: each consecutive failure doubles the hold-off, and a
    success clears it. Hammering an endpoint that is already returning 429s
    or 503s is what turns throttling into a block.

    The delay is drawn uniformly from ``[0, base * factor ** failures)``,
    capped at ``maximum`` -- the "full jitter" strategy. The randomness
    matters more than the ceiling when several workers fail together, since
    a fixed delay would send them all back at the same instant.

    Failures are reported automatically, so it needs no wiring beyond being
    gated through:

    ```python
    @restrain("api", Backoff(base=0.5, maximum=60.0))
    def fetch(): ...
    ```

    By default any exception counts as a failure. Narrow that with
    ``failure_on`` to avoid backing off on a bug in your own code:

    ```python
    Backoff(base=1.0, failure_on=(httpx.HTTPStatusError, httpx.TimeoutException))
    ```

    Args:
        base: Delay after a single failure, before jitter.
        factor: Multiplier applied per consecutive failure.
        maximum: Ceiling on the delay.
        failure_on: Exception types that count as failures.
        clock: Monotonic seconds source. Injected by tests.
        sleep: Blocking sleep used by :meth:`gate`. Injected by tests.
        rng: Random source. Injected by tests.

    Raises:
        ValueError: ``base`` is not positive, ``factor`` is less than one, or
            ``maximum`` is below ``base``.
    """

    def __init__(
        self,
        base: float = 0.5,
        *,
        factor: float = 2.0,
        maximum: float = 60.0,
        failure_on: type[BaseException] | tuple[type[BaseException], ...] = Exception,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        """Initialise the backoff schedule."""
        super().__init__(clock=clock, sleep=sleep)
        if base <= 0:
            raise ValueError("base must be positive")
        if factor < 1:
            raise ValueError("factor must be at least 1")
        if maximum < base:
            raise ValueError("maximum must not be less than base")
        self.base = base
        self.factor = factor
        self.maximum = maximum
        self.failure_on = failure_on
        self._rng = rng or random.Random()  # noqa: S311 - pacing, not crypto
        self._failures = 0
        self._until: float | None = None

    @property
    def failures(self) -> int:
        """Consecutive failures seen since the last success."""
        with self._lock:
            return self._failures

    def _reserve(self) -> Reservation:
        """Wait out any hold-off currently in force."""
        if self._until is None:
            return Reservation()
        remaining = self._until - self._clock()
        if remaining <= 0:
            self._until = None
            return Reservation()
        # Not granted: a failure reported while we wait extends the hold-off,
        # and re-checking is what lets that take effect.
        return Reservation(remaining, granted=False)

    def report(self, outcome: Outcome) -> None:
        """Extend the hold-off on failure, or clear it on success."""
        with self._lock:
            if outcome.exception is not None and isinstance(
                outcome.exception, self.failure_on
            ):
                self._failures += 1
                ceiling = min(
                    self.maximum, self.base * self.factor ** (self._failures - 1)
                )
                self._until = self._clock() + self._rng.uniform(0.0, ceiling)
            else:
                self._failures = 0
                self._until = None
