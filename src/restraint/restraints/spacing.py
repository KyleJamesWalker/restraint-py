"""Minimum spacing and random dither between calls."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from restraint.restraints.base import Reservation, Restraint

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["Jitter", "Spacing"]


class Spacing(Restraint):
    """Enforce a minimum gap between consecutive calls.

    A rate limit says how many calls fit in a window; spacing says how close
    together two of them may be. That is the difference between five requests
    spread over a second and five fired in the same millisecond, and it is
    the shape a server sees.

    Slots are reserved rather than contended for, so concurrent callers queue
    in order instead of waking together and racing. Each gap is measured from
    when the previous call actually started rather than when it was scheduled
    to, so lateness does not accumulate across a run.

    Add ``jitter`` to break up the cadence. Perfectly periodic traffic is a
    cheap thing to spot, and identical intervals across a worker pool make
    every worker hit the same boundary at once.

    ```python
    Spacing(seconds=0.5, jitter=0.25)  # a call every 500-750ms
    ```

    Args:
        seconds: Minimum gap between calls.
        jitter: Upper bound on extra delay added to each gap, drawn
            uniformly from ``[0, jitter)``.
        clock: Monotonic seconds source. Injected by tests.
        sleep: Blocking sleep used by :meth:`gate`. Injected by tests.
        rng: Random source. Injected by tests.

    Note:
        ``seconds`` is a target, not a floor, when callers are concurrent.
        A queued caller has already reserved its slot, so if the call ahead
        of it resumes late the gap between the two is short by that lateness.
        Measured at 8 threads against a 50ms setting, the worst observed gap
        was 45ms. Set the gap with margin rather than at the server's exact
        threshold.

    Raises:
        ValueError: ``seconds`` or ``jitter`` is negative.
    """

    def __init__(
        self,
        seconds: float,
        *,
        jitter: float = 0.0,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        """Initialise the spacing."""
        super().__init__(clock=clock, sleep=sleep)
        if seconds < 0:
            raise ValueError("seconds must not be negative")
        if jitter < 0:
            raise ValueError("jitter must not be negative")
        self.seconds = seconds
        self.jitter = jitter
        self._rng = rng or random.Random()  # noqa: S311 - pacing, not crypto
        self._next_allowed: float | None = None

    def _gap(self) -> float:
        """Return the gap to enforce for the next call."""
        if not self.jitter:
            return self.seconds
        return self.seconds + self._rng.uniform(0.0, self.jitter)

    def _reserve(self) -> Reservation:
        """Reserve the next slot and report how long until it opens."""
        now = self._clock()
        earliest = now if self._next_allowed is None else max(now, self._next_allowed)
        gap = self._gap()
        self._next_allowed = earliest + gap
        return Reservation(max(earliest - now, 0.0), granted=True, token=float(gap))

    def _admitted(self, token: object) -> None:
        """Measure the next gap from when this call really started.

        Measuring from the predicted slot let a late wake-up shorten the
        following gap, so the observed spacing came in under the configured
        minimum.
        """
        # `token is not None` rather than an isinstance check: Spacing(seconds=1)
        # yields an int gap, which an isinstance(float) test would skip.
        if token is not None:
            gap = float(token)  # type: ignore[arg-type]
            self._next_allowed = max(self._next_allowed or 0.0, self._clock() + gap)


class Jitter(Restraint):
    """Delay every call by a random amount.

    Useful on its own to desynchronise a fleet of workers that would
    otherwise start together, and composes with any other restraint.

    Args:
        seconds: Upper bound on the delay.
        minimum: Lower bound on the delay.
        clock: Monotonic seconds source. Unused, accepted for symmetry.
        sleep: Blocking sleep used by :meth:`gate`. Injected by tests.
        rng: Random source. Injected by tests.

    Raises:
        ValueError: The bounds are negative or inverted.
    """

    def __init__(
        self,
        seconds: float,
        *,
        minimum: float = 0.0,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        """Initialise the jitter bounds."""
        super().__init__(clock=clock, sleep=sleep)
        if minimum < 0:
            raise ValueError("minimum must not be negative")
        if seconds < minimum:
            raise ValueError("seconds must not be less than minimum")
        self.seconds = seconds
        self.minimum = minimum
        self._rng = rng or random.Random()  # noqa: S311 - pacing, not crypto

    def _reserve(self) -> Reservation:
        """Admit the call after a random delay."""
        return Reservation(self._rng.uniform(self.minimum, self.seconds), granted=True)
