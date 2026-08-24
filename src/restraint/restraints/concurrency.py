"""Cap on calls in flight at once."""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

from restraint.restraints.base import Reservation, Restraint

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["Concurrency"]

#: How often a waiting caller re-checks for its turn.
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

    Waiters are served strictly in arrival order. Each takes a ticket on
    arrival and may claim a slot only when its ticket comes up, so a caller
    that releases and immediately re-acquires goes to the back of the queue
    instead of beating everyone already waiting.

    One counter serves both threads and coroutines, so a mixed program is
    still held to ``limit`` overall. Threads block on a condition variable;
    coroutines re-check every ``poll`` seconds, which keeps the single shared
    counter without ever blocking the event loop.

    Args:
        limit: Maximum calls in flight.
        poll: How often a waiting coroutine re-checks its turn, and the
            longest a blocked thread sleeps before re-checking.
        clock: Monotonic seconds source. Unused, accepted for symmetry.
        sleep: Unused; waiting is handled by the queue rather than by
            sleeping for a computed interval.

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
        self._issued = 0
        self._serving = 0
        self._abandoned: set[int] = set()
        self._turn = threading.Condition(self._lock)

    @property
    def in_flight(self) -> int:
        """How many gated calls are currently running."""
        with self._lock:
            return self._in_flight

    @property
    def waiting(self) -> int:
        """How many callers are queued for a slot."""
        with self._lock:
            return max(self._issued - self._serving - len(self._abandoned), 0)

    def _take_ticket(self) -> int:
        """Join the back of the queue."""
        with self._lock:
            ticket = self._issued
            self._issued += 1
            return ticket

    def _skip_abandoned(self) -> None:
        """Advance past tickets whose owner gave up. Caller holds the lock."""
        while self._serving in self._abandoned:
            self._abandoned.discard(self._serving)
            self._serving += 1

    def _claim(self, ticket: int) -> bool:
        """Take a slot if this ticket's turn has come. Caller holds the lock."""
        self._skip_abandoned()
        if ticket == self._serving and self._in_flight < self.limit:
            self._in_flight += 1
            self._serving += 1
            self._skip_abandoned()
            self._turn.notify_all()
            return True
        return False

    def _abandon(self, ticket: int) -> None:
        """Drop out of the queue without ever being served."""
        with self._turn:
            self._abandoned.add(ticket)
            self._skip_abandoned()
            self._turn.notify_all()

    def gate(self) -> None:
        """Block until a slot is free and this caller's turn has come."""
        ticket = self._take_ticket()
        try:
            with self._turn:
                while not self._claim(ticket):
                    # Bounded wait: a coroutine ahead of us in the queue only
                    # re-checks on its own poll interval and cannot notify us
                    # while it sleeps.
                    self._turn.wait(self.poll)
        except BaseException:
            self._abandon(ticket)
            raise

    async def agate(self) -> None:
        """Await a free slot without blocking the event loop."""
        ticket = self._take_ticket()
        try:
            while True:
                with self._turn:
                    if self._claim(ticket):
                        return
                await asyncio.sleep(self.poll)
        except BaseException:
            self._abandon(ticket)
            raise

    def _reserve(self) -> Reservation:
        """Unused: admission is queued rather than reserved per attempt."""
        raise NotImplementedError

    def release(self) -> None:
        """Give the slot back once the gated call has finished."""
        with self._turn:
            if self._in_flight > 0:
                self._in_flight -= 1
            self._turn.notify_all()
