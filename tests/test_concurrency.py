"""Test the in-flight cap."""

import asyncio
import threading

import pytest

from restraint import Concurrency, restrain


def test_slots_are_taken_and_returned() -> None:
    limiter = Concurrency(2)
    limiter.gate()
    limiter.gate()
    assert limiter.in_flight == 2

    limiter.release()
    assert limiter.in_flight == 1


def test_full_cap_refuses_until_released() -> None:
    limiter = Concurrency(1)
    limiter.gate()

    reservation = limiter._reserve()
    assert not reservation.granted
    assert reservation.wait == pytest.approx(limiter.poll)

    limiter.release()
    assert limiter._reserve().granted


def test_release_never_goes_negative() -> None:
    limiter = Concurrency(1)
    limiter.release()
    limiter.release()
    assert limiter.in_flight == 0


def test_context_manager_returns_the_slot() -> None:
    limiter = Concurrency(1)
    with restrain("conc-cm", limiter):
        assert limiter.in_flight == 1
    assert limiter.in_flight == 0


def test_slot_is_returned_when_the_body_raises() -> None:
    limiter = Concurrency(1)
    with pytest.raises(ValueError, match="boom"), restrain("conc-raise", limiter):
        raise ValueError("boom")
    assert limiter.in_flight == 0


def test_decorator_returns_the_slot() -> None:
    limiter = Concurrency(1)

    @restrain("conc-dec", limiter)
    def work() -> int:
        assert limiter.in_flight == 1
        return 1

    assert work() == 1
    assert limiter.in_flight == 0


def test_threads_never_exceed_the_cap() -> None:
    limiter = Concurrency(3)
    peak = 0
    peak_lock = threading.Lock()
    start = threading.Barrier(12)

    def worker() -> None:
        nonlocal peak
        start.wait()
        with restrain("conc-threads", limiter):
            with peak_lock:
                peak = max(peak, limiter.in_flight)
            threading.Event().wait(0.01)

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert peak <= 3
    assert limiter.in_flight == 0


async def test_coroutines_never_exceed_the_cap() -> None:
    limiter = Concurrency(2)
    peak = 0

    @restrain("conc-async", limiter)
    async def work() -> None:
        nonlocal peak
        peak = max(peak, limiter.in_flight)
        await asyncio.sleep(0.01)

    await asyncio.gather(*(work() for _ in range(8)))

    assert peak <= 2
    assert limiter.in_flight == 0


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"limit": 0}, "limit must be at least 1"),
        ({"limit": 1, "poll": 0.0}, "poll must be positive"),
    ],
)
def test_rejects_invalid_configuration(kwargs: dict[str, float], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Concurrency(**kwargs)  # type: ignore[arg-type]
