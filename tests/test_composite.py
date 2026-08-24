"""Test combining restraints."""

import pytest

from restraint import (
    Adaptive,
    Composite,
    Concurrency,
    Outcome,
    Quota,
    Spacing,
    TokenBucket,
    restrain,
)
from restraint.exceptions import QuotaExceededError

from .conftest import FakeClock


def test_and_builds_a_composite() -> None:
    combined = TokenBucket(rate=1.0) & Spacing(seconds=1.0)
    assert isinstance(combined, Composite)
    assert len(combined) == 2


def test_and_flattens_rather_than_nesting() -> None:
    """`a & b & c` should be one composite, not a tree of pairs."""
    combined = TokenBucket(rate=1.0) & Spacing(seconds=1.0) & Concurrency(1)
    assert len(combined) == 3
    assert not any(isinstance(member, Composite) for member in combined)


def test_and_rejects_non_restraints() -> None:
    with pytest.raises(TypeError):
        TokenBucket(rate=1.0) & "nope"  # type: ignore[operator]


def test_empty_composite_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one restraint"):
        Composite()


def test_repr_lists_members() -> None:
    combined = Composite(Quota(day=1), Spacing(seconds=1.0))
    assert repr(combined) == "<Composite Quota & Spacing>"


def test_strictest_member_wins(clock: FakeClock) -> None:
    """Two rate rules compose to the tighter of the two."""
    combined = Composite(
        TokenBucket(rate=100.0, clock=clock.monotonic, sleep=clock.sleep),
        Spacing(seconds=2.0, clock=clock.monotonic, sleep=clock.sleep),
    )
    combined.gate()
    combined.gate()
    assert clock.slept == [pytest.approx(2.0)]


def test_quota_refuses_before_the_bucket_is_spent(clock: FakeClock) -> None:
    """Ordering the cheap rejection first is why order matters."""
    bucket = TokenBucket(rate=10.0, clock=clock.monotonic, sleep=clock.sleep)
    combined = Composite(Quota(second=1, now=clock.now), bucket)

    combined.gate()
    spent = bucket.tokens

    with pytest.raises(QuotaExceededError):
        combined.gate()

    assert bucket.tokens == pytest.approx(spent), "a refused call must cost no token"


def test_earlier_slots_are_released_when_a_later_member_refuses(
    clock: FakeClock,
) -> None:
    """A composite must not leak a concurrency slot on refusal."""
    slots = Concurrency(2)
    combined = Composite(slots, Quota(second=1, now=clock.now))

    combined.gate()
    combined.release()
    assert slots.in_flight == 0

    with pytest.raises(QuotaExceededError):
        combined.gate()
    assert slots.in_flight == 0, "refusal leaked a slot"


def test_release_returns_every_member(clock: FakeClock) -> None:
    first, second = Concurrency(2), Concurrency(2)
    combined = Composite(first, second)
    combined.gate()
    assert (first.in_flight, second.in_flight) == (1, 1)

    combined.release()
    assert (first.in_flight, second.in_flight) == (0, 0)


def test_outcome_reaches_every_member(clock: FakeClock) -> None:
    adaptive = Adaptive(clock=clock.monotonic, sleep=clock.sleep)
    combined = Composite(TokenBucket(rate=100.0), adaptive)
    combined.report(
        Outcome(headers={"X-RateLimit-Remaining": "6", "X-RateLimit-Reset": "60"})
    )
    assert adaptive.gap == pytest.approx(10.0)


def test_works_through_restrain(clock: FakeClock) -> None:
    slots = Concurrency(1)
    adaptive = Adaptive(clock=clock.monotonic, sleep=clock.sleep)

    with restrain("composite-cm", slots & adaptive) as gate:
        assert slots.in_flight == 1
        gate.observe(200, {"X-RateLimit-Remaining": "2", "X-RateLimit-Reset": "60"})

    assert slots.in_flight == 0
    assert adaptive.gap == pytest.approx(30.0)


async def test_async_path_gates_every_member() -> None:
    slots = Concurrency(1)
    combined = slots & TokenBucket(rate=1000.0)

    await combined.agate()
    assert slots.in_flight == 1
    combined.release()
    assert slots.in_flight == 0


async def test_async_refusal_releases_earlier_members(clock: FakeClock) -> None:
    slots = Concurrency(2)
    combined = Composite(slots, Quota(second=1, now=clock.now))

    await combined.agate()
    combined.release()

    with pytest.raises(QuotaExceededError):
        await combined.agate()
    assert slots.in_flight == 0
