"""Test calendar window arithmetic."""

import datetime

import pytest

from restraint._calendar import floor, next_boundary


@pytest.mark.parametrize(
    ("period", "expected"),
    [
        ("year", datetime.datetime(2020, 1, 1, 0, 0, 0)),
        ("month", datetime.datetime(2020, 7, 1, 0, 0, 0)),
        ("day", datetime.datetime(2020, 7, 15, 0, 0, 0)),
        ("hour", datetime.datetime(2020, 7, 15, 13, 0, 0)),
        ("minute", datetime.datetime(2020, 7, 15, 13, 42, 0)),
        ("second", datetime.datetime(2020, 7, 15, 13, 42, 9)),
    ],
)
def test_floor(period: str, expected: datetime.datetime) -> None:
    moment = datetime.datetime(2020, 7, 15, 13, 42, 9, 123456)
    assert floor(moment, period) == expected


@pytest.mark.parametrize(
    ("period", "expected"),
    [
        ("year", datetime.datetime(2021, 1, 1)),
        ("month", datetime.datetime(2020, 8, 1)),
        ("day", datetime.datetime(2020, 7, 16)),
        ("hour", datetime.datetime(2020, 7, 15, 14)),
        ("minute", datetime.datetime(2020, 7, 15, 13, 43)),
        ("second", datetime.datetime(2020, 7, 15, 13, 42, 10)),
    ],
)
def test_next_boundary(period: str, expected: datetime.datetime) -> None:
    moment = datetime.datetime(2020, 7, 15, 13, 42, 9, 123456)
    assert next_boundary(moment, period) == expected


def test_december_rolls_into_january() -> None:
    moment = datetime.datetime(2020, 12, 25, 6, 0, 0)
    assert next_boundary(moment, "month") == datetime.datetime(2021, 1, 1)


def test_leap_day_is_a_normal_day() -> None:
    moment = datetime.datetime(2020, 2, 29, 23, 59, 59)
    assert next_boundary(moment, "day") == datetime.datetime(2020, 3, 1)


class TestBackwardsClock:
    """A clock that steps backwards must not hand back spent allowance."""

    def test_limit_is_not_refilled_by_a_backwards_step(self) -> None:
        from restraint import Limit

        moment = [datetime.datetime(2020, 11, 1, 1, 30, 0)]
        lmt = Limit(hour=2, now=lambda: moment[0], sleep=lambda _: None)
        lmt.gate()
        lmt.gate()
        assert lmt.remaining() == {"hour": 0}

        # DST fall-back: 01:30 happens twice.
        moment[0] = datetime.datetime(2020, 11, 1, 0, 45, 0)
        assert lmt.remaining() == {"hour": 0}, "a backwards clock refilled the window"

    def test_quota_is_not_doubled_by_a_backwards_step(self) -> None:
        from restraint import Quota
        from restraint.exceptions import QuotaExceededError

        moment = [datetime.datetime(2020, 11, 1, 12, 0, 0)]
        quota = Quota(day=2, now=lambda: moment[0])
        quota.gate()
        quota.gate()

        moment[0] = datetime.datetime(2020, 10, 31, 12, 0, 0)
        with pytest.raises(QuotaExceededError):
            quota.gate()

        # And stepping forward again must not count as a second fresh window.
        moment[0] = datetime.datetime(2020, 11, 1, 12, 0, 0)
        with pytest.raises(QuotaExceededError):
            quota.gate()

    def test_a_genuinely_later_window_still_refills(self) -> None:
        from restraint import Quota

        moment = [datetime.datetime(2020, 11, 1, 12, 0, 0)]
        quota = Quota(day=1, now=lambda: moment[0])
        quota.gate()

        moment[0] = datetime.datetime(2020, 11, 2, 12, 0, 0)
        quota.gate()
