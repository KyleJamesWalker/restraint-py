"""Calendar-aligned call limits."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from restraint._calendar import CalendarWindows
from restraint.restraints.base import Reservation, Restraint

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["Limit"]


def _now() -> datetime.datetime:
    """Return the current local wall-clock time."""
    return datetime.datetime.now()


class Limit(Restraint):
    """Fixed-window limit that refills at the top of each calendar period.

    Allowances reset on period boundaries, so the full quota is available
    immediately at the start of every window. That is the point -- it drains
    quota as fast as the server permits -- but it also means a boundary can
    admit up to twice the rate back to back. Reach for
    :class:`~restraint.restraints.bucket.TokenBucket` or
    :class:`~restraint.restraints.window.SlidingWindow` when smooth pacing
    matters more than draining the window.

    Multiple periods compose: ``Limit(second=2, minute=30)`` allows two calls
    a second up to thirty a minute.

    Windows follow the system's local wall clock, so a daylight-saving change
    shifts the boundaries of ``hour`` and coarser periods.

    Args:
        second: Calls allowed per calendar second.
        minute: Calls allowed per calendar minute.
        hour: Calls allowed per calendar hour.
        day: Calls allowed per calendar day.
        month: Calls allowed per calendar month.
        year: Calls allowed per calendar year.
        now: Wall-clock source. Injected by tests.
        sleep: Blocking sleep used by :meth:`gate`. Injected by tests.
    """

    def __init__(
        self,
        second: int = 0,
        minute: int = 0,
        hour: int = 0,
        day: int = 0,
        month: int = 0,
        year: int = 0,
        *,
        now: Callable[[], datetime.datetime] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        """Initialise the limit from per-period allowances."""
        super().__init__(sleep=sleep)
        self._now = now or _now
        caps = {
            period: value
            for period, value in (
                ("year", year),
                ("month", month),
                ("day", day),
                ("hour", hour),
                ("minute", minute),
                ("second", second),
            )
            if value
        }
        self._windows = CalendarWindows(caps)

    @property
    def caps(self) -> dict[str, int]:
        """The configured allowance per period."""
        return self._windows.caps

    def remaining(self) -> dict[str, int]:
        """Return the allowance left in each period's current window."""
        with self._lock:
            return self._windows.remaining(self._now())

    def _reserve(self) -> Reservation:
        """Consume one call, or report the wait until a window refills."""
        now = self._now()
        exhausted = self._windows.exhausted(now)
        if exhausted:
            # Not granted: after sleeping we re-check, because a coarser
            # window may still be empty once the finer one has refilled.
            return Reservation(self._windows.retry_after(now, exhausted), granted=False)
        self._windows.consume(now)
        return Reservation()
