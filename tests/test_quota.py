"""Test hard budget caps."""

import datetime

import pytest

from restraint import Quota, restrain
from restraint.exceptions import QuotaExceededError

from .conftest import FakeClock


def test_spends_then_refuses(clock: FakeClock) -> None:
    """A spent quota raises rather than parking the caller for a day."""
    quota = Quota(day=2, now=clock.now)
    quota.gate()
    quota.gate()

    with pytest.raises(QuotaExceededError, match="day quota of 2 is spent"):
        quota.gate()

    assert clock.slept == []


def test_refills_on_the_window(clock: FakeClock) -> None:
    quota = Quota(day=1, now=clock.now)
    quota.gate()
    with pytest.raises(QuotaExceededError):
        quota.gate()

    clock.advance(datetime.timedelta(days=1).total_seconds())
    quota.gate()


def test_remaining_reports_budget(clock: FakeClock) -> None:
    quota = Quota(hour=3, day=10, now=clock.now)
    assert quota.remaining() == {"day": 10, "hour": 3}
    quota.gate()
    assert quota.remaining() == {"day": 9, "hour": 2}


def test_error_names_the_refill_delay(clock: FakeClock) -> None:
    quota = Quota(minute=1, now=clock.now)
    quota.gate()
    with pytest.raises(QuotaExceededError, match=r"refills in \d+s"):
        quota.gate()


def test_works_through_restrain(clock: FakeClock) -> None:
    quota = Quota(second=1, now=clock.now)
    with restrain("quota-cm", quota):
        pass

    with pytest.raises(QuotaExceededError), restrain("quota-cm"):
        pass


def test_no_caps_never_refuses(clock: FakeClock) -> None:
    quota = Quota(now=clock.now)
    for _ in range(100):
        quota.gate()


async def test_async_path_also_refuses(clock: FakeClock) -> None:
    quota = Quota(second=1, now=clock.now)
    await quota.agate()
    with pytest.raises(QuotaExceededError):
        await quota.agate()


def test_caps_are_a_copy(clock: FakeClock) -> None:
    quota = Quota(day=5, now=clock.now)
    quota.caps["day"] = 99
    assert quota.caps == {"day": 5}
