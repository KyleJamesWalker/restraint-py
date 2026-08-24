"""Global test fixtures."""

import datetime

import pytest


class FakeClock:
    """Deterministic wall clock that only moves when a test moves it."""

    def __init__(self, start: datetime.datetime) -> None:
        """Start the clock at ``start``."""
        self.moment = start
        self.slept: list[float] = []

    def now(self) -> datetime.datetime:
        """Return the current fake time."""
        return self.moment

    def monotonic(self) -> float:
        """Return the fake time as monotonic seconds."""
        return self.moment.timestamp()

    def sleep(self, seconds: float) -> None:
        """Record a sleep and advance the clock by it."""
        self.slept.append(seconds)
        self.moment += datetime.timedelta(seconds=seconds)

    def advance(self, seconds: float) -> None:
        """Move the clock forward without recording a sleep."""
        self.moment += datetime.timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    """A fake clock pinned to the timestamp the original suite used."""
    return FakeClock(datetime.datetime(2020, 1, 15, 7, 9, 1, 313375))
