"""Test the sliding window."""

import pytest

from restraint import SlidingWindow

from .conftest import FakeClock


def build(clock: FakeClock, **kwargs: float) -> SlidingWindow:
    """Build a window driven by the fake clock."""
    return SlidingWindow(clock=clock.monotonic, sleep=clock.sleep, **kwargs)  # type: ignore[arg-type]


def test_allowance_then_wait(clock: FakeClock) -> None:
    window = build(clock, limit=3, per=1.0)
    for _ in range(3):
        window.gate()
    assert clock.slept == []

    window.gate()
    assert clock.slept == [pytest.approx(1.0)]


def test_admissions_age_out(clock: FakeClock) -> None:
    window = build(clock, limit=2, per=1.0)
    window.gate()
    window.gate()
    assert window.in_window() == 2

    clock.advance(1.1)
    assert window.in_window() == 0
    window.gate()
    assert clock.slept == []


def test_no_boundary_double_burst(clock: FakeClock) -> None:
    """A rolling window cannot be straddled the way a calendar one can."""
    window = build(clock, limit=3, per=1.0)
    clock.advance(0.98)

    admitted = 0
    for _ in range(10):
        if window._reserve().wait == 0.0:
            admitted += 1
            clock.advance(0.001)
        else:
            break

    assert admitted == 3


def test_partial_expiry_releases_one_slot(clock: FakeClock) -> None:
    window = build(clock, limit=2, per=1.0)
    window.gate()
    clock.advance(0.5)
    window.gate()

    clock.advance(0.6)  # only the first admission has aged out
    assert window.in_window() == 1
    window.gate()
    assert clock.slept == []


def test_queued_callers_are_served_in_order(clock: FakeClock) -> None:
    window = build(clock, limit=1, per=1.0)
    waits = [window._reserve().wait for _ in range(4)]
    assert waits == [pytest.approx(w) for w in (0.0, 1.0, 2.0, 3.0)]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"limit": 0}, "limit must be at least 1"),
        ({"limit": 1, "per": 0.0}, "per must be positive"),
    ],
)
def test_rejects_invalid_configuration(kwargs: dict[str, float], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        SlidingWindow(**kwargs)  # type: ignore[arg-type]


async def test_async_path_paces(clock: FakeClock) -> None:
    window = SlidingWindow(limit=2, per=0.01)
    for _ in range(3):
        await window.agate()


def test_admission_is_timestamped_when_the_caller_resumes(clock: FakeClock) -> None:
    """Counting the predicted slot let entries age out early.

    The window then held fewer entries than it should and admitted over the
    limit; 16 threads against limit=50 saw 57-59 in a one-second window.
    """
    window = build(clock, limit=1, per=1.0)

    reservation = window._reserve()
    assert reservation.wait == 0.0
    # The caller resumes later than the reservation predicted.
    clock.advance(0.4)
    window._admitted(reservation.token)

    # The entry must age out 1.0s after the real start, not the prediction.
    clock.advance(0.9)
    assert window.in_window() == 1, "entry aged out early"
    clock.advance(0.2)
    assert window.in_window() == 0
