"""Pacing driven by the server's own rate-limit signals."""

from __future__ import annotations

import email.utils
import time
from typing import TYPE_CHECKING

from restraint.restraints.base import Reservation, Restraint

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from restraint.outcome import Outcome

__all__ = ["Adaptive"]

#: Status codes that mean "you are being throttled".
THROTTLE_STATUSES = frozenset({429, 503})

#: A reset value above this is read as an absolute epoch timestamp rather
#: than a delta. No API expresses a window as ~11 days of seconds, and
#: GitHub, Reddit and X all report the reset moment as epoch seconds.
EPOCH_RESET_THRESHOLD = 1_000_000.0


def _parse_retry_after(value: str) -> float | None:
    """Parse a ``Retry-After`` value, which may be seconds or a HTTP date."""
    try:
        return max(float(value.strip()), 0.0)
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    # The header is absolute but the restraint runs on a monotonic clock, so
    # convert to a delay rather than a timestamp.
    return max(when.timestamp() - time.time(), 0.0)


class Adaptive(Restraint):
    """Obey the rate-limit budget the server reports.

    Every other restraint guesses at the server's limit from configuration.
    This one reads it: ``X-RateLimit-Remaining`` and ``X-RateLimit-Reset``
    say how much budget is left and when it refills, which is enough to
    spread the remaining calls across the remaining window instead of
    draining them and stalling. ``Retry-After`` is obeyed outright.

    It needs to be told what came back, since the library never sees the
    response:

    ```python
    with restrain("api", Adaptive()) as gate:
        response = httpx.get(url)
        gate.observe(response.status_code, response.headers)
    ```

    Knowing nothing, it does nothing -- pair it with a configured restraint
    so the first calls are still paced:

    ```python
    TokenBucket(rate=5) & Adaptive()
    ```

    Header names vary between APIs; override them if yours differ.

    Args:
        minimum: Floor on the computed gap between calls, so a server
            reporting a huge budget cannot remove all pacing.
        maximum: Ceiling on any single wait, including ``Retry-After`` and
            the gap computed from the reported budget.
        throttle_hold: Hold-off applied when the server reports throttling
            but gives no ``Retry-After`` and no budget headers.
        reset_style: How to read the reset header -- ``"delta"`` for
            seconds from now, ``"epoch"`` for an absolute timestamp, or
            ``"auto"`` to choose per value.
        remaining_header: Header naming the calls left in the window.
        reset_header: Header naming the seconds until the window resets.
        retry_after_header: Header naming an explicit hold-off.
        clock: Monotonic seconds source. Injected by tests.
        sleep: Blocking sleep used by :meth:`gate`. Injected by tests.

    Raises:
        ValueError: ``minimum`` is negative or ``maximum`` is below it.
    """

    def __init__(
        self,
        *,
        minimum: float = 0.0,
        maximum: float = 300.0,
        throttle_hold: float = 1.0,
        reset_style: str = "auto",
        remaining_header: str = "X-RateLimit-Remaining",
        reset_header: str = "X-RateLimit-Reset",
        retry_after_header: str = "Retry-After",
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        """Initialise the adaptive pacer."""
        super().__init__(clock=clock, sleep=sleep)
        if minimum < 0:
            raise ValueError("minimum must not be negative")
        if maximum < minimum:
            raise ValueError("maximum must not be less than minimum")
        if throttle_hold < 0:
            raise ValueError("throttle_hold must not be negative")
        if reset_style not in {"auto", "delta", "epoch"}:
            raise ValueError("reset_style must be auto, delta or epoch")
        self.minimum = minimum
        self.maximum = maximum
        self.throttle_hold = throttle_hold
        self.reset_style = reset_style
        self.remaining_header = remaining_header
        self.reset_header = reset_header
        self.retry_after_header = retry_after_header
        self._gap = minimum
        self._next_allowed: float | None = None
        self._hold_until: float | None = None

    @property
    def gap(self) -> float:
        """The gap currently being enforced between calls."""
        with self._lock:
            return self._gap

    def _reserve(self) -> Reservation:
        """Wait out any hold-off, then honour the computed gap."""
        now = self._clock()
        if self._hold_until is not None:
            remaining = self._hold_until - now
            if remaining > 0:
                # Not granted: a fresh Retry-After may extend the hold.
                return Reservation(min(remaining, self.maximum), granted=False)
            self._hold_until = None
        if not self._gap:
            return Reservation()
        earliest = now if self._next_allowed is None else max(now, self._next_allowed)
        self._next_allowed = earliest + self._gap
        wait = min(max(earliest - now, 0.0), self.maximum)
        return Reservation(wait, granted=True)

    @staticmethod
    def _lookup(headers: Mapping[str, str], name: str) -> str | None:
        """Read a header case-insensitively."""
        if name in headers:
            return headers[name]
        lowered = name.lower()
        return next((v for k, v in headers.items() if k.lower() == lowered), None)

    def report(self, outcome: Outcome) -> None:
        """Re-pace from the budget the server just reported."""
        with self._lock:
            now = self._clock()
            hold = outcome.retry_after
            headers = outcome.headers or {}

            if hold is None and (raw := self._lookup(headers, self.retry_after_header)):
                hold = _parse_retry_after(raw)
            if hold is None and outcome.status in THROTTLE_STATUSES:
                # Throttled without being told for how long. Being refused is
                # itself information, so never fall through to no hold at all.
                hold = max(self._gap, self.minimum, self.throttle_hold)
            if hold is not None:
                self._hold_until = now + min(hold, self.maximum)

            self._repace(headers)

    def _repace(self, headers: Mapping[str, str]) -> None:
        """Spread the reported remaining budget across the reported window."""
        raw_remaining = self._lookup(headers, self.remaining_header)
        raw_reset = self._lookup(headers, self.reset_header)
        if raw_remaining is None or raw_reset is None:
            return
        try:
            remaining = int(float(raw_remaining))
            reset_in = self._reset_seconds(float(raw_reset))
        except ValueError:
            return
        if reset_in <= 0:
            self._gap = self.minimum
            return
        # One call left means wait out the window; zero means it is already
        # spent, so treat both as the full remaining window.
        gap = max(reset_in / max(remaining, 1), self.minimum)
        self._gap = min(gap, self.maximum)

    def _reset_seconds(self, value: float) -> float:
        """Convert a reset header value into seconds from now."""
        if self.reset_style == "delta":
            return value
        if self.reset_style == "epoch" or value > EPOCH_RESET_THRESHOLD:
            return max(value - time.time(), 0.0)
        return value
