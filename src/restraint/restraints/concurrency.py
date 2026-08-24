"""Cap on calls in flight at once."""

from __future__ import annotations

from typing import TYPE_CHECKING

from restraint.restraints.base import Reservation, Restraint

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["Concurrency"]

#: How long a blocked caller waits before re-checking for a free slot.
DEFAULT_POLL = 0.005


class Concurrency(Restraint):
    """Limit how many gated calls may be in flight simultaneously.

    Orthogonal to rate: a rate limit caps how often calls start, this caps
    how many are running. A pool of workers against a slow endpoint can sit
    well inside its rate limit and still hold hundreds of open connections.

    The slot is held until the gated call finishes, so this only works where
    the library can see completion -- the decorator, ``with``, and
    ``async with``. Calling :meth:`gate` directly requires a matching
    :meth:`release`.

    ```python
    @restrain("scrape", Concurrency(4))
    async def fetch(url): ...
    ```

    One counter serves both threads and coroutines, so a mixed program is
    still held to ``limit`` overall. Blocked callers re-check every ``poll``
    seconds rather than being handed off directly, which keeps the same
    counter usable from either world.

    Args:
        limit: Maximum calls in flight.
        poll: How long a blocked caller waits between checks.
        clock: Monotonic seconds source. Unused, accepted for symmetry.
        sleep: Blocking sleep used by :meth:`gate`. Injected by tests.

    Raises:
        ValueError: ``limit`` is less than one or ``poll`` is not positive.
    """

    def __init__(
        self,
        limit: int,
        *,
        poll: float = DEFAULT_POLL,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        """Initialise the concurrency cap."""
        super().__init__(clock=clock, sleep=sleep)
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if poll <= 0:
            raise ValueError("poll must be positive")
        self.limit = limit
        self.poll = poll
        self._in_flight = 0

    @property
    def in_flight(self) -> int:
        """How many gated calls are currently running."""
        with self._lock:
            return self._in_flight

    def _reserve(self) -> Reservation:
        """Take a slot if one is free, otherwise ask to be retried."""
        if self._in_flight < self.limit:
            self._in_flight += 1
            return Reservation()
        return Reservation(self.poll, granted=False)

    def release(self) -> None:
        """Give the slot back once the gated call has finished."""
        with self._lock:
            if self._in_flight > 0:
                self._in_flight -= 1
