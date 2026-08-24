"""Calendar window arithmetic for period-aligned restraints."""

from __future__ import annotations

import datetime

__all__ = ["PERIODS", "CalendarWindows"]

#: Supported window granularities, coarsest first.
PERIODS: tuple[str, ...] = ("year", "month", "day", "hour", "minute", "second")

#: Fields zeroed (or set to 1, for month and day) when truncating to a period.
_FLOOR: dict[str, dict[str, int]] = {
    "year": {
        "month": 1,
        "day": 1,
        "hour": 0,
        "minute": 0,
        "second": 0,
        "microsecond": 0,
    },
    "month": {"day": 1, "hour": 0, "minute": 0, "second": 0, "microsecond": 0},
    "day": {"hour": 0, "minute": 0, "second": 0, "microsecond": 0},
    "hour": {"minute": 0, "second": 0, "microsecond": 0},
    "minute": {"second": 0, "microsecond": 0},
    "second": {"microsecond": 0},
}


def floor(moment: datetime.datetime, period: str) -> datetime.datetime:
    """Truncate ``moment`` down to the start of its ``period`` window."""
    return moment.replace(**_FLOOR[period])  # type: ignore[arg-type]


def next_boundary(moment: datetime.datetime, period: str) -> datetime.datetime:
    """Return the start of the ``period`` window after the one holding ``moment``."""
    start = floor(moment, period)
    if period == "year":
        return start.replace(year=start.year + 1)
    if period == "month":
        if start.month == 12:
            return start.replace(year=start.year + 1, month=1)
        return start.replace(month=start.month + 1)
    return start + datetime.timedelta(**{f"{period}s": 1})


class CalendarWindows:
    """Per-period counters that refill at the top of each calendar window.

    Tracks a cap per granularity and the window each count belongs to, so a
    ``minute`` allowance refills at the top of the minute rather than a
    rolling sixty seconds. Callers are expected to hold a lock.
    """

    def __init__(self, caps: dict[str, int]) -> None:
        """Initialise counters from a mapping of period name to cap.

        Args:
            caps: Allowance per period, e.g. ``{"second": 5, "day": 1000}``.
                Periods absent from the mapping are unrestricted.
        """
        self._caps = caps
        self._remaining = dict(caps)
        self._windows: dict[str, datetime.datetime] = {}

    @property
    def caps(self) -> dict[str, int]:
        """The configured allowance per period."""
        return dict(self._caps)

    def remaining(self, now: datetime.datetime) -> dict[str, int]:
        """Return the allowance left per period, refilling expired windows."""
        self._refill(now)
        return dict(self._remaining)

    def _refill(self, now: datetime.datetime) -> None:
        """Reset any counter whose window no longer contains ``now``."""
        for period, cap in self._caps.items():
            window = floor(now, period)
            if self._windows.get(period) != window:
                self._windows[period] = window
                self._remaining[period] = cap

    def exhausted(self, now: datetime.datetime) -> list[str]:
        """Return the periods with no allowance left, coarsest first."""
        self._refill(now)
        return [p for p in PERIODS if self._remaining.get(p, 1) < 1]

    def consume(self, now: datetime.datetime) -> None:
        """Take one unit from every configured period."""
        self._refill(now)
        for period in self._remaining:
            self._remaining[period] -= 1

    def retry_after(self, now: datetime.datetime, exhausted: list[str]) -> float:
        """Seconds until every exhausted period has refilled.

        The coarsest exhausted period refills last, so its boundary is the
        one that matters.
        """
        boundary = max(next_boundary(now, period) for period in exhausted)
        return max((boundary - now).total_seconds(), 0.0)
