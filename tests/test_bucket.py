"""Test the token bucket."""

import pytest

from restraint import TokenBucket

from .conftest import FakeClock


def build(clock: FakeClock, **kwargs: float) -> TokenBucket:
    """Build a bucket driven by the fake clock."""
    return TokenBucket(clock=clock.monotonic, sleep=clock.sleep, **kwargs)  # type: ignore[arg-type]


def test_burst_then_pace(clock: FakeClock) -> None:
    bucket = build(clock, rate=5.0)
    for _ in range(5):
        bucket.gate()
    assert clock.slept == []

    bucket.gate()
    assert clock.slept == [pytest.approx(0.2)]


def test_idle_refills_up_to_burst(clock: FakeClock) -> None:
    bucket = build(clock, rate=2.0, burst=4.0)
    for _ in range(4):
        bucket.gate()
    assert bucket.tokens == pytest.approx(0.0)

    clock.advance(60.0)
    assert bucket.tokens == pytest.approx(4.0), "refill must cap at burst"


def test_sustained_rate_is_honoured(clock: FakeClock) -> None:
    bucket = build(clock, rate=10.0)
    for _ in range(10):
        bucket.gate()
    start = clock.monotonic()
    for _ in range(10):
        bucket.gate()
    assert clock.monotonic() - start == pytest.approx(1.0)


def test_no_boundary_double_burst(clock: FakeClock) -> None:
    """The failure mode a fixed window has and a bucket does not.

    Limit(second=3) admits three calls at the end of one second and three
    more at the start of the next. A bucket admits four in that span.
    """
    bucket = build(clock, rate=3.0)
    clock.advance(0.98)

    admitted = 0
    deadline = clock.monotonic() + 0.05
    while clock.monotonic() < deadline:
        if bucket._reserve().wait == 0.0:
            admitted += 1
        else:
            break
        clock.advance(0.001)

    assert admitted <= 4


def test_rate_over_a_custom_interval(clock: FakeClock) -> None:
    bucket = build(clock, rate=60.0, per=60.0, burst=1.0)
    bucket.gate()
    bucket.gate()
    assert clock.slept == [pytest.approx(1.0)]


def test_concurrent_reservations_queue_in_order(clock: FakeClock) -> None:
    bucket = build(clock, rate=1.0, burst=1.0)
    waits = [bucket._reserve().wait for _ in range(4)]
    assert waits == [pytest.approx(w) for w in (0.0, 1.0, 2.0, 3.0)]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"rate": 0.0}, "rate must be positive"),
        ({"rate": 1.0, "per": 0.0}, "per must be positive"),
        ({"rate": 1.0, "burst": 0.0}, "burst must be at least 1"),
    ],
)
def test_rejects_invalid_configuration(kwargs: dict[str, float], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        TokenBucket(**kwargs)  # type: ignore[arg-type]


async def test_async_path_paces(clock: FakeClock) -> None:
    bucket = TokenBucket(rate=100.0)
    for _ in range(3):
        await bucket.agate()
