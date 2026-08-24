"""Hard budget caps that refuse rather than wait."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from restraint._calendar import CalendarWindows
from restraint.exceptions import QuotaExceededError
from restraint.restraints.base import Reservation, Restraint

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["Quota"]


def _now() -> datetime.datetime:
    """Return the current local wall-clock time."""
    return datetime.datetime.now()


class Quota(Restraint):
    """A spend cap that raises when exhausted instead of blocking.

    :class:`~restraint.restraints.limit.Limit` waits for the next window,
    which is the right answer for a per-second rate and the wrong one for a
    budget: ``Limit(day=1000)`` parks a worker for hours and ``Limit(month=…)``
    for weeks, with nothing to distinguish that from a hang. A quota is the
    restraint to reach for when running out is an error, not a delay.

    ```python
    with restrain("api", Quota(day=10_000)):
        ...
    ```

    Compose it ahead of a pacing restraint so the budget is checked before
    anything else is spent:

    ```python
    Quota(day=10_000) & TokenBucket(rate=5)
    ```

    Args:
        second: Calls allowed per calendar second.
        minute: Calls allowed per calendar minute.
        hour: Calls allowed per calendar hour.
        day: Calls allowed per calendar day.
        month: Calls allowed per calendar month.
        year: Calls allowed per calendar year.
        now: Wall-clock source. Injected by tests.

    Note:
        Counters live in memory, so a restart refills them. A long-horizon
        cap is only as durable as the process holding it.
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
    ) -> None:
        """Initialise the quota from per-period allowances."""
        super().__init__()
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
        """Return the budget left in each period's current window."""
        with self._lock:
            return self._windows.remaining(self._now())

    def _reserve(self) -> Reservation:
        """Spend one call, or refuse outright.

        Raises:
            QuotaExceededError: The budget for some period is spent.
        """
        now = self._now()
        exhausted = self._windows.exhausted(now)
        if exhausted:
            retry_after = self._windows.retry_after(now, exhausted)
            period = exhausted[0]
            raise QuotaExceededError(
                f"{period} quota of {self._windows.caps[period]} is spent; "
                f"refills in {retry_after:.0f}s"
            )
        self._windows.consume(now)
        return Reservation()
