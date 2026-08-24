"""Shared machinery for every restraint."""

from __future__ import annotations

import asyncio
import threading
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Callable

    from restraint.outcome import Outcome

__all__ = ["Reservation", "Restraint"]


class Reservation(NamedTuple):
    """The result of asking a restraint for permission to proceed.

    Attributes:
        wait: Seconds the caller must sleep before doing anything else.
        granted: Whether capacity was claimed. When False the caller must
            sleep and ask again; when True the sleep is the reserved delay
            and the call may proceed once it elapses.
    """

    wait: float = 0.0
    granted: bool = True


#: Capacity was available immediately.
_ADMIT = Reservation()


class Restraint(ABC):
    """Base class implementing the gate loop shared by all restraints.

    Subclasses implement :meth:`_reserve`, which runs under a lock and either
    claims capacity or reports how long to wait. The base class turns that
    into a blocking :meth:`gate` and an ``await``-able :meth:`agate` without
    the subclass having to know which world it is running in.

    Reserving under a lock but sleeping outside it is what makes a restraint
    safe to share between threads: only the reservation needs to be atomic.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        """Initialise the shared gate machinery.

        Args:
            clock: Monotonic seconds source. Injected by tests.
            sleep: Blocking sleep used by :meth:`gate`. Injected by tests.
        """
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        # Re-entrant so a subclass may call its own helpers while reserving.
        self._lock = threading.RLock()

    @abstractmethod
    def _reserve(self) -> Reservation:
        """Claim capacity for one call, or report how long to wait.

        Called with ``self._lock`` held, so implementations may read and
        mutate their own state without further synchronisation.
        """

    def gate(self) -> None:
        """Block until this call is allowed to proceed."""
        while True:
            with self._lock:
                reservation = self._reserve()
            if reservation.wait > 0.0:
                self._sleep(reservation.wait)
            if reservation.granted:
                return

    async def agate(self) -> None:
        """Await until this call is allowed to proceed.

        Yields to the event loop while waiting instead of blocking it.
        """
        while True:
            with self._lock:
                reservation = self._reserve()
            if reservation.wait > 0.0:
                await asyncio.sleep(reservation.wait)
            if reservation.granted:
                return

    def release(self) -> None:  # noqa: B027 - optional hook, no-op by default
        """Give back anything held for the duration of the gated call."""

    def report(self, outcome: Outcome) -> None:  # noqa: B027 - optional hook
        """Observe how a gated call turned out.

        Restraints that adapt to the server, such as
        :class:`~restraint.restraints.backoff.Backoff` and
        :class:`~restraint.restraints.adaptive.Adaptive`, override this.

        Args:
            outcome: What happened to the call this restraint admitted.
        """

    def __and__(self, other: Restraint) -> Restraint:
        """Compose two restraints so a call must satisfy both."""
        from restraint.restraints.composite import Composite

        if not isinstance(other, Restraint):
            return NotImplemented
        return Composite(self, other)
