"""Combining restraints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from restraint.restraints.base import Reservation, Restraint

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from restraint.outcome import Outcome

__all__ = ["Composite"]


class Composite(Restraint):
    """Apply several restraints to the same call, in order.

    Real pacing is usually more than one rule: a budget that must not be
    exceeded, a rate to hold, a gap to keep, and a reaction to being
    throttled. Build that by combining single-purpose restraints with ``&``:

    ```python
    polite = (
        Quota(day=10_000)           # refuse once the budget is gone
        & TokenBucket(rate=5)       # hold five a second
        & Spacing(seconds=0.05, jitter=0.05)
        & Adaptive()                # then do as the server says
    )

    with restrain("api", polite) as gate:
        response = httpx.get(url)
        gate.observe(response.status_code, response.headers)
    ```

    Order matters. Members are gated left to right, so put the cheapest
    rejection first: a :class:`~restraint.restraints.quota.Quota` placed
    ahead of a bucket refuses before a token is spent, while the reverse
    wastes the token. Slots are released in reverse order, and every member
    is told the outcome.

    Because members are gated in sequence rather than reserved together, a
    caller can be holding an earlier member's capacity while waiting on a
    later one. Ordering broad limits before narrow ones keeps that short.

    Args:
        *restraints: The restraints to apply, in gating order.

    Raises:
        ValueError: No restraints were given.
    """

    def __init__(self, *restraints: Restraint) -> None:
        """Flatten and store the members."""
        super().__init__()
        flattened: list[Restraint] = []
        for restraint in restraints:
            # Flatten so `a & b & c` is one composite, not nested pairs.
            if isinstance(restraint, Composite):
                flattened.extend(restraint.restraints)
            else:
                flattened.append(restraint)
        if not flattened:
            raise ValueError("Composite needs at least one restraint")
        self._restraints = tuple(flattened)

    @property
    def restraints(self) -> Sequence[Restraint]:
        """The members, in gating order."""
        return self._restraints

    def __iter__(self) -> Iterator[Restraint]:
        """Iterate over the members in gating order."""
        return iter(self._restraints)

    def __len__(self) -> int:
        """Return how many members there are."""
        return len(self._restraints)

    def __repr__(self) -> str:
        """Show the members in gating order."""
        members = " & ".join(type(r).__name__ for r in self._restraints)
        return f"<Composite {members}>"

    def _reserve(self) -> Reservation:
        """Unused: gating is delegated to each member in turn."""
        raise NotImplementedError

    def gate(self) -> None:
        """Block until every member has admitted the call."""
        admitted: list[Restraint] = []
        try:
            for restraint in self._restraints:
                restraint.gate()
                admitted.append(restraint)
        except BaseException:
            # A later member refused, so give back what the earlier ones held.
            self._release(admitted)
            raise

    async def agate(self) -> None:
        """Await until every member has admitted the call."""
        admitted: list[Restraint] = []
        try:
            for restraint in self._restraints:
                await restraint.agate()
                admitted.append(restraint)
        except BaseException:
            self._release(admitted)
            raise

    @staticmethod
    def _release(restraints: Sequence[Restraint]) -> None:
        """Release the given restraints in reverse order."""
        for restraint in reversed(restraints):
            restraint.release()

    def release(self) -> None:
        """Release every member, in reverse gating order."""
        self._release(self._restraints)

    def report(self, outcome: Outcome) -> None:
        """Tell every member how the call turned out."""
        for restraint in self._restraints:
            restraint.report(outcome)
