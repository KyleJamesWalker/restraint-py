"""Test pacing from server rate-limit headers."""

import pytest

from restraint import Adaptive, Outcome, restrain

from .conftest import FakeClock


def build(clock: FakeClock, **kwargs: float) -> Adaptive:
    """Build an adaptive pacer driven by the fake clock."""
    return Adaptive(clock=clock.monotonic, sleep=clock.sleep, **kwargs)  # type: ignore[arg-type]


def test_knowing_nothing_it_does_nothing(clock: FakeClock) -> None:
    adaptive = build(clock)
    for _ in range(10):
        adaptive.gate()
    assert clock.slept == []


def test_paces_remaining_budget_across_the_window(clock: FakeClock) -> None:
    """10 calls left and 60s to go means one call every 6 seconds."""
    adaptive = build(clock)
    adaptive.report(
        Outcome(headers={"X-RateLimit-Remaining": "10", "X-RateLimit-Reset": "60"})
    )
    assert adaptive.gap == pytest.approx(6.0)

    adaptive.gate()
    adaptive.gate()
    assert clock.slept == [pytest.approx(6.0)]


def test_pacing_tightens_and_loosens(clock: FakeClock) -> None:
    adaptive = build(clock)
    adaptive.report(
        Outcome(headers={"X-RateLimit-Remaining": "100", "X-RateLimit-Reset": "60"})
    )
    assert adaptive.gap == pytest.approx(0.6)

    adaptive.report(
        Outcome(headers={"X-RateLimit-Remaining": "2", "X-RateLimit-Reset": "60"})
    )
    assert adaptive.gap == pytest.approx(30.0)


def test_exhausted_budget_waits_out_the_window(clock: FakeClock) -> None:
    adaptive = build(clock)
    adaptive.report(
        Outcome(headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "45"})
    )
    assert adaptive.gap == pytest.approx(45.0)


def test_retry_after_seconds_is_obeyed(clock: FakeClock) -> None:
    adaptive = build(clock)
    adaptive.report(Outcome(status=429, headers={"Retry-After": "30"}))

    adaptive.gate()
    assert clock.slept == [pytest.approx(30.0)]


def test_retry_after_http_date_is_obeyed(clock: FakeClock) -> None:
    adaptive = build(clock)
    adaptive.report(
        Outcome(status=429, headers={"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"})
    )
    adaptive.gate()
    assert clock.slept, "a date-form Retry-After must still hold the caller"


def test_unparseable_retry_after_falls_back_to_the_gap(clock: FakeClock) -> None:
    adaptive = build(clock, minimum=2.0)
    adaptive.report(Outcome(status=429, headers={"Retry-After": "soon-ish"}))
    adaptive.gate()
    assert clock.slept == [pytest.approx(2.0)]


def test_throttled_without_a_header_still_holds(clock: FakeClock) -> None:
    adaptive = build(clock, minimum=1.5)
    adaptive.report(Outcome(status=503))
    adaptive.gate()
    assert clock.slept == [pytest.approx(1.5)]


def test_explicit_retry_after_beats_the_header(clock: FakeClock) -> None:
    adaptive = build(clock)
    adaptive.report(Outcome(headers={"Retry-After": "99"}, retry_after=5.0))
    adaptive.gate()
    assert clock.slept == [pytest.approx(5.0)]


def test_hold_is_capped(clock: FakeClock) -> None:
    adaptive = build(clock, maximum=10.0)
    adaptive.report(Outcome(status=429, headers={"Retry-After": "3600"}))
    adaptive.gate()
    assert clock.slept == [pytest.approx(10.0)]


def test_minimum_floors_the_gap(clock: FakeClock) -> None:
    adaptive = build(clock, minimum=1.0)
    adaptive.report(
        Outcome(headers={"X-RateLimit-Remaining": "10000", "X-RateLimit-Reset": "60"})
    )
    assert adaptive.gap == pytest.approx(1.0)


def test_headers_are_case_insensitive(clock: FakeClock) -> None:
    adaptive = build(clock)
    adaptive.report(
        Outcome(headers={"x-ratelimit-remaining": "6", "x-ratelimit-reset": "60"})
    )
    assert adaptive.gap == pytest.approx(10.0)


def test_custom_header_names(clock: FakeClock) -> None:
    adaptive = Adaptive(
        remaining_header="RateLimit-Remaining",
        reset_header="RateLimit-Reset",
        clock=clock.monotonic,
        sleep=clock.sleep,
    )
    adaptive.report(
        Outcome(headers={"RateLimit-Remaining": "4", "RateLimit-Reset": "60"})
    )
    assert adaptive.gap == pytest.approx(15.0)


def test_garbage_headers_are_ignored(clock: FakeClock) -> None:
    adaptive = build(clock)
    adaptive.report(
        Outcome(headers={"X-RateLimit-Remaining": "lots", "X-RateLimit-Reset": "soon"})
    )
    assert adaptive.gap == pytest.approx(0.0)


def test_zero_reset_drops_back_to_the_floor(clock: FakeClock) -> None:
    """A window reported as already reset carries no pacing information."""
    adaptive = build(clock, minimum=0.5)
    adaptive.report(
        Outcome(headers={"X-RateLimit-Remaining": "5", "X-RateLimit-Reset": "0"})
    )
    assert adaptive.gap == pytest.approx(0.5)


def test_partial_headers_are_ignored(clock: FakeClock) -> None:
    adaptive = build(clock)
    adaptive.report(Outcome(headers={"X-RateLimit-Remaining": "5"}))
    assert adaptive.gap == pytest.approx(0.0)


def test_reads_headers_through_the_gate(clock: FakeClock) -> None:
    """The whole point: observe() on the gate re-paces the restraint."""
    adaptive = build(clock)
    with restrain("adaptive-cm", adaptive) as gate:
        gate.observe(200, {"X-RateLimit-Remaining": "5", "X-RateLimit-Reset": "60"})

    assert adaptive.gap == pytest.approx(12.0)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"minimum": -1.0}, "minimum must not be negative"),
        ({"minimum": 5.0, "maximum": 1.0}, "maximum must not be less than minimum"),
    ],
)
def test_rejects_invalid_configuration(kwargs: dict[str, float], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Adaptive(**kwargs)  # type: ignore[arg-type]


async def test_async_path_honours_the_hold(clock: FakeClock) -> None:
    adaptive = Adaptive(maximum=0.02)
    adaptive.report(Outcome(status=429, headers={"Retry-After": "1"}))
    await adaptive.agate()
