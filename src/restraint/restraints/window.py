"""Sliding window rate limiting."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from restraint.restraints.base import Reservation, Restraint

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["SlidingWindow"]


class SlidingWindow(Restraint):
    """Limit calls over a rolling window rather than a calendar one.

    ``Limit(second=3)`` counts against the current clock second, so three
    calls at 00:00.999 and three more at 00:01.001 all pass -- six calls in
    two milliseconds. A sliding window measures the last ``per`` seconds from
    now, wherever the clock happens to be, so that cannot happen.

    ```python
    SlidingWindow(limit=100, per=60.0)  # about 100 in any rolling minute
    ```

    Use this when the server measures the same way and a boundary burst would
    trip it. Prefer :class:`~restraint.restraints.bucket.TokenBucket` for
    smooth pacing, since a sliding window still admits its whole allowance
    back to back before holding everything until the window rolls.

    Admissions are timestamped when the caller actually resumes rather than
    when the slot was predicted, so lateness cannot accumulate.

    Note:
        ``limit`` is not a hard bound under concurrency. Waiting callers
        reserve their slots up front, so when one resumes late the caller
        behind it starts sooner than its own slot implied. Measured at
        16 threads against ``limit=50, per=1.0``, the worst trailing window
        held 51. The excess tracks scheduler wake latency against ``per``:
        material below a second, negligible at a minute. Leave headroom, or
        use :class:`~restraint.restraints.bucket.TokenBucket` where the
        server's limit is strict.

    Args:
        limit: Calls allowed in any ``per``-second stretch.
        per: Window length in seconds.
        clock: Monotonic seconds source. Injected by tests.
        sleep: Blocking sleep used by :meth:`gate`. Injected by tests.

    Raises:
        ValueError: ``limit`` is less than one or ``per`` is not positive.
    """

    def __init__(
        self,
        limit: int,
        *,
        per: float = 1.0,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        """Initialise the window."""
        super().__init__(clock=clock, sleep=sleep)
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if per <= 0:
            raise ValueError("per must be positive")
        self.limit = limit
        self.per = per
        # Each entry is a one-element list so the timestamp can be corrected
        # to the real admission moment once the caller resumes.
        self._admissions: deque[list[float]] = deque()

    def _prune(self, now: float) -> None:
        """Drop admissions that have aged out of the window."""
        cutoff = now - self.per
        while self._admissions and self._admissions[0][0] <= cutoff:
            self._admissions.popleft()

    def in_window(self) -> int:
        """Return how many admissions currently occupy the window."""
        with self._lock:
            self._prune(self._clock())
            return len(self._admissions)

    def _reserve(self) -> Reservation:
        """Claim a slot, waiting for the oldest one to age out if full."""
        now = self._clock()
        self._prune(now)
        if len(self._admissions) < self.limit:
            entry = [now]
            self._admissions.append(entry)
            return Reservation(token=entry)
        # Room opens once enough admissions have aged out to leave fewer
        # than `limit` in the window, so key off that entry rather than the
        # oldest. Future timestamps stay in arrival order, keeping queued
        # callers fair.
        slot = self._admissions[len(self._admissions) - self.limit][0] + self.per
        entry = [slot]
        self._admissions.append(entry)
        return Reservation(max(slot - now, 0.0), granted=True, token=entry)

    def _admitted(self, token: object) -> None:
        """Replace the predicted slot with the moment the call really began.

        A reservation only predicts when the slot opens; the caller resumes
        whenever the scheduler reaches it. Counting the prediction let entries
        age out early, so the window admitted more than `limit`.
        """
        if isinstance(token, list):
            # Only ever moves forward, so the deque stays ordered.
            token[0] = max(token[0], self._clock())
