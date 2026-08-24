"""Test the in-flight cap."""

import asyncio
import threading
import time

import pytest

from restraint import Concurrency, restrain


def test_slots_are_taken_and_returned() -> None:
    limiter = Concurrency(2)
    limiter.gate()
    limiter.gate()
    assert limiter.in_flight == 2

    limiter.release()
    assert limiter.in_flight == 1


def test_full_cap_blocks_until_released() -> None:
    limiter = Concurrency(1)
    limiter.gate()

    admitted = threading.Event()
    waiter = threading.Thread(target=lambda: (limiter.gate(), admitted.set()))
    waiter.start()

    assert not admitted.wait(0.05), "a second caller entered a full cap"
    assert limiter.waiting == 1

    limiter.release()
    assert admitted.wait(1.0), "releasing did not admit the waiter"
    waiter.join()
    assert limiter.in_flight == 1


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


def test_waiters_are_served_in_arrival_order() -> None:
    """A releasing holder must not be able to jump the queue.

    Polling with no queue let a caller that released and immediately
    re-acquired win every time, starving everyone waiting.
    """
    limiter = Concurrency(1)
    limiter.gate()

    order: list[int] = []
    order_lock = threading.Lock()
    started = [threading.Event() for _ in range(4)]

    def worker(index: int) -> None:
        started[index].set()
        limiter.gate()
        with order_lock:
            order.append(index)
        limiter.release()

    threads = []
    for index in range(4):
        thread = threading.Thread(target=worker, args=(index,))
        threads.append(thread)
        thread.start()
        # Let each one join the queue before the next arrives.
        started[index].wait(1.0)
        time.sleep(0.02)

    limiter.release()
    for thread in threads:
        thread.join(timeout=5.0)
        assert not thread.is_alive(), "a waiter never got a slot"

    assert order == [0, 1, 2, 3], f"served out of order: {order}"


def test_a_churning_holder_cannot_starve_a_waiter() -> None:
    """Reproduces the reported hang: re-acquiring goes to the back."""
    limiter = Concurrency(1)
    admitted = threading.Event()
    stop = threading.Event()

    def churner() -> None:
        while not stop.is_set():
            limiter.gate()
            limiter.release()

    def waiter() -> None:
        limiter.gate()
        admitted.set()
        limiter.release()

    churn = threading.Thread(target=churner, daemon=True)
    churn.start()
    time.sleep(0.02)
    wait_thread = threading.Thread(target=waiter)
    wait_thread.start()

    got_in = admitted.wait(5.0)
    stop.set()
    wait_thread.join(timeout=5.0)
    churn.join(timeout=5.0)

    assert got_in, "the waiter was starved by a churning holder"


def test_abandoning_the_queue_does_not_block_it() -> None:
    """A cancelled waiter must not wedge everyone behind it."""
    limiter = Concurrency(1)
    limiter.gate()

    ticket = limiter._take_ticket()
    limiter._abandon(ticket)

    limiter.release()
    limiter.gate()
    assert limiter.in_flight == 1


async def test_cancelled_coroutine_releases_its_place() -> None:
    limiter = Concurrency(1)
    await limiter.agate()

    task = asyncio.create_task(limiter.agate())
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    limiter.release()
    # The abandoned ticket must not block a later arrival.
    await asyncio.wait_for(limiter.agate(), timeout=2.0)
    assert limiter.in_flight == 1
