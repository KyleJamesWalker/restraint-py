"""Test spacing and jitter."""

import random

import pytest

from restraint import Jitter, Spacing

from .conftest import FakeClock


def build(clock: FakeClock, **kwargs: float) -> Spacing:
    """Build Spacing driven by the fake clock."""
    return Spacing(clock=clock.monotonic, sleep=clock.sleep, **kwargs)  # type: ignore[arg-type]


def test_first_call_is_immediate(clock: FakeClock) -> None:
    spacing = build(clock, seconds=1.0)
    spacing.gate()
    assert clock.slept == []


def test_subsequent_calls_are_spaced(clock: FakeClock) -> None:
    spacing = build(clock, seconds=0.5)
    spacing.gate()
    spacing.gate()
    spacing.gate()
    assert clock.slept == [pytest.approx(0.5), pytest.approx(0.5)]


def test_idle_time_counts_towards_the_gap(clock: FakeClock) -> None:
    """A caller that waited longer than the gap is not delayed again."""
    spacing = build(clock, seconds=0.5)
    spacing.gate()
    clock.advance(2.0)
    spacing.gate()
    assert clock.slept == []


def test_slots_are_reserved_so_callers_queue(clock: FakeClock) -> None:
    """Back-to-back reservations stack instead of collapsing onto one slot."""
    spacing = build(clock, seconds=1.0)
    waits = [spacing._reserve().wait for _ in range(4)]
    assert waits == [0.0, 1.0, 2.0, 3.0]


def test_jitter_widens_the_gap(clock: FakeClock) -> None:
    spacing = Spacing(
        seconds=1.0,
        jitter=1.0,
        clock=clock.monotonic,
        sleep=clock.sleep,
        rng=random.Random(0),
    )
    spacing.gate()
    spacing.gate()
    assert 1.0 <= clock.slept[0] < 2.0


def test_jitter_varies_between_calls(clock: FakeClock) -> None:
    spacing = Spacing(
        seconds=0.0,
        jitter=1.0,
        clock=clock.monotonic,
        sleep=clock.sleep,
        rng=random.Random(1),
    )
    for _ in range(6):
        spacing.gate()
    assert len(set(clock.slept)) > 1, "identical gaps defeat the point of jitter"


@pytest.mark.parametrize(
    "kwargs",
    [{"seconds": -1.0}, {"seconds": 1.0, "jitter": -1.0}],
)
def test_spacing_rejects_negative_bounds(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        Spacing(**kwargs)  # type: ignore[arg-type]


def test_jitter_delays_within_bounds(clock: FakeClock) -> None:
    jit = Jitter(
        seconds=0.5,
        minimum=0.1,
        clock=clock.monotonic,
        sleep=clock.sleep,
        rng=random.Random(2),
    )
    for _ in range(20):
        jit.gate()
    assert all(0.1 <= s <= 0.5 for s in clock.slept)
    assert len(clock.slept) == 20


def test_jitter_rejects_inverted_bounds() -> None:
    with pytest.raises(ValueError, match="not be less than minimum"):
        Jitter(seconds=0.1, minimum=1.0)


async def test_spacing_paces_the_async_path(clock: FakeClock) -> None:
    spacing = Spacing(seconds=0.01)
    await spacing.agate()
    await spacing.agate()


def test_next_gap_is_measured_from_the_real_start(clock: FakeClock) -> None:
    """A late resume must not shorten the following gap."""
    spacing = build(clock, seconds=1.0)

    reservation = spacing._reserve()
    clock.advance(0.5)  # resumed late
    spacing._admitted(reservation.token)

    # The next slot is a full gap after the real start, not the prediction.
    assert spacing._reserve().wait == pytest.approx(1.0)


def test_integer_seconds_still_correct_the_gap(clock: FakeClock) -> None:
    """An int gap must not slip past the correction.

    Guarding the token with isinstance(float) silently skipped Spacing(1).
    """
    spacing = build(clock, seconds=1)

    reservation = spacing._reserve()
    clock.advance(0.5)
    spacing._admitted(reservation.token)

    assert spacing._reserve().wait == pytest.approx(1.0)
