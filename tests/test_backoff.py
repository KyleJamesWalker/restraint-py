"""Test outcome-driven backoff."""

import random

import pytest

from restraint import Backoff, Outcome, restrain

from .conftest import FakeClock


def build(clock: FakeClock, seed: int = 0, **kwargs: object) -> Backoff:
    """Build a backoff driven by the fake clock and a seeded rng."""
    return Backoff(
        clock=clock.monotonic,
        sleep=clock.sleep,
        rng=random.Random(seed),
        **kwargs,  # type: ignore[arg-type]
    )


def test_success_never_holds_back(clock: FakeClock) -> None:
    backoff = build(clock)
    for _ in range(5):
        backoff.gate()
        backoff.report(Outcome())
    assert clock.slept == []


def test_failure_holds_the_next_call(clock: FakeClock) -> None:
    backoff = build(clock, base=1.0)
    backoff.gate()
    backoff.report(Outcome(exception=RuntimeError("429")))

    backoff.gate()
    assert clock.slept
    assert 0.0 <= clock.slept[0] <= 1.0


def test_consecutive_failures_escalate(clock: FakeClock) -> None:
    backoff = build(clock, base=1.0, maximum=1000.0)
    ceilings = []
    for _ in range(5):
        backoff.report(Outcome(exception=RuntimeError("nope")))
        ceilings.append(backoff._until - clock.monotonic())
        clock.advance(ceilings[-1])

    assert backoff.failures == 5
    # Each round's jittered delay is drawn from a ceiling twice the last.
    assert max(ceilings) > min(ceilings)


def test_delay_is_capped(clock: FakeClock) -> None:
    backoff = build(clock, base=1.0, maximum=2.0)
    for _ in range(20):
        backoff.report(Outcome(exception=RuntimeError("nope")))
        assert backoff._until - clock.monotonic() <= 2.0


def test_success_clears_the_hold(clock: FakeClock) -> None:
    backoff = build(clock, base=5.0)
    backoff.report(Outcome(exception=RuntimeError("nope")))
    assert backoff.failures == 1

    backoff.report(Outcome())
    assert backoff.failures == 0
    backoff.gate()
    assert clock.slept == []


def test_unlisted_exceptions_do_not_trigger_backoff(clock: FakeClock) -> None:
    """A bug in our own code should not be mistaken for server throttling."""
    backoff = build(clock, base=1.0, failure_on=TimeoutError)
    backoff.report(Outcome(exception=ValueError("our bug")))
    assert backoff.failures == 0

    backoff.report(Outcome(exception=TimeoutError("theirs")))
    assert backoff.failures == 1


def test_decorator_reports_failures(clock: FakeClock) -> None:
    backoff = build(clock, base=1.0)

    @restrain("backoff-dec", backoff)
    def flaky() -> None:
        raise RuntimeError("429")

    with pytest.raises(RuntimeError, match="429"):
        flaky()
    assert backoff.failures == 1


def test_jitter_spreads_retries(clock: FakeClock) -> None:
    """Identical delays would send a whole fleet back at the same instant."""
    delays = set()
    for seed in range(8):
        backoff = build(clock, seed=seed, base=10.0)
        backoff.report(Outcome(exception=RuntimeError("nope")))
        delays.add(round(backoff._until - clock.monotonic(), 6))
    assert len(delays) > 1


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"base": 0.0}, "base must be positive"),
        ({"base": 1.0, "factor": 0.5}, "factor must be at least 1"),
        ({"base": 5.0, "maximum": 1.0}, "maximum must not be less than base"),
    ],
)
def test_rejects_invalid_configuration(kwargs: dict[str, float], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Backoff(**kwargs)  # type: ignore[arg-type]


async def test_async_path_waits_out_the_hold(clock: FakeClock) -> None:
    backoff = Backoff(base=0.01, maximum=0.02)
    backoff.report(Outcome(exception=RuntimeError("nope")))
    await backoff.agate()
    assert backoff._until is None
