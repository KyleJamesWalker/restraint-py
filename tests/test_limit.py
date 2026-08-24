"""Test calendar-aligned limits."""

import datetime
import threading

import pytest

from restraint import Limit

from .conftest import FakeClock


def build(clock: FakeClock, **caps: int) -> Limit:
    """Build a Limit driven entirely by the fake clock."""
    return Limit(now=clock.now, sleep=clock.sleep, **caps)


def test_seconds(clock: FakeClock) -> None:
    """A second allowance drains, then waits for the next second boundary."""
    lmt = build(clock, second=3)

    for _ in range(3):
        lmt.gate()
    assert clock.slept == []

    lmt.gate()
    assert clock.slept == [0.686625]


def test_minutes(clock: FakeClock) -> None:
    """Second and minute windows interact exactly as they did in 0.0.2.

    These are the original 0.0.2 expectations, kept verbatim so the rewrite
    onto the reservation protocol is provably behaviour-preserving.
    """
    lmt = build(clock, second=1, minute=3)
    # A hair of extra delay so consecutive calls do not land on one instant.
    lmt._sleep = lambda s: (clock.slept.append(s), clock.advance(s + 0.0001))[0]

    expected: list[float] = []
    for wait in (None, 0.686625, 0.9999, 56.9999, 0.9999, 0.9999, 57.9999):
        lmt.gate()
        if wait is not None:
            expected.append(wait)
        assert clock.slept == expected


def test_no_caps_never_waits(clock: FakeClock) -> None:
    """A limit with no configured period is a no-op."""
    lmt = build(clock)
    for _ in range(100):
        lmt.gate()
    assert clock.slept == []


def test_remaining_reports_allowance(clock: FakeClock) -> None:
    """Remaining allowance is visible and refills on the boundary."""
    lmt = build(clock, second=2, minute=5)
    assert lmt.remaining() == {"minute": 5, "second": 2}

    lmt.gate()
    assert lmt.remaining() == {"minute": 4, "second": 1}

    clock.advance(1)
    assert lmt.remaining() == {"minute": 4, "second": 2}


def test_coarse_window_gates_after_fine_refills(clock: FakeClock) -> None:
    """An exhausted minute keeps gating even once the second has refilled."""
    lmt = build(clock, second=5, minute=2)
    lmt.gate()
    lmt.gate()

    lmt.gate()
    # Waited to the top of the next minute, not the next second.
    assert clock.slept == [pytest.approx(58.686625)]


def test_month_boundary_rolls_the_year(clock: FakeClock) -> None:
    """A December month window refills on 1 January."""
    lmt = Limit(
        month=1,
        now=lambda: datetime.datetime(2020, 12, 31, 23, 59, 59),
        sleep=lambda _: None,
    )
    lmt.gate()
    reservation = lmt._reserve()
    assert not reservation.granted
    assert reservation.wait == pytest.approx(1.0)


def test_caps_are_a_copy(clock: FakeClock) -> None:
    """Mutating the reported caps cannot corrupt the limit."""
    lmt = build(clock, second=1)
    lmt.caps["second"] = 99
    assert lmt.caps == {"second": 1}


def test_threads_cannot_exceed_the_allowance() -> None:
    """Concurrent callers are held to the configured rate.

    Before the reservation protocol this admitted all twenty callers at once,
    because check-then-decrement was not atomic.
    """
    admitted = 0
    admitted_lock = threading.Lock()
    start = threading.Barrier(20)

    lmt = Limit(second=5, sleep=lambda _: None)

    def worker() -> None:
        nonlocal admitted
        start.wait()
        if lmt._reserve().granted:
            with admitted_lock:
                admitted += 1

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert admitted == 5
