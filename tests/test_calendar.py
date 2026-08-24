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
