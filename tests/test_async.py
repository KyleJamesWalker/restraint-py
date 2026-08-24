"""Test async gating."""

import asyncio

import pytest

from restraint import (
    Gate,
    Limit,
    Outcome,
    Reservation,
    Restraint,
    RestraintError,
    add,
    restrain,
)


class Delay(Restraint):
    """Admits every call, but only after a fixed reserved delay."""

    def __init__(self, wait: float) -> None:
        super().__init__()
        self.wait = wait
        self.reported: list[Outcome] = []
        self.releases = 0

    def _reserve(self) -> Reservation:
        return Reservation(self.wait, granted=True)

    def report(self, outcome: Outcome) -> None:
        self.reported.append(outcome)

    def release(self) -> None:
        self.releases += 1


async def count_ticks(interval: float, stop: asyncio.Event) -> int:
    """Tick until told to stop, reporting how many times the loop ran us."""
    ticks = 0
    while not stop.is_set():
        await asyncio.sleep(interval)
        ticks += 1
    return ticks


async def test_async_context_manager_admits() -> None:
    """`async with` used to raise TypeError: NoneType can't be awaited."""
    entered = False
    async with restrain("actx", Delay(0.0)) as gate:
        entered = True
        assert isinstance(gate, Gate)
    assert entered


async def test_agate_yields_to_the_event_loop() -> None:
    """Waiting must not block the loop.

    The 0.0.2 async decorator called the blocking gate, so a coroutine
    waiting on quota froze every other task in the loop.
    """
    restraint = Delay(0.2)
    stop = asyncio.Event()
    heartbeat = asyncio.create_task(count_ticks(0.01, stop))

    await restraint.agate()

    stop.set()
    ticks = await heartbeat
    assert ticks > 5, f"event loop only ran the heartbeat {ticks} times"


async def test_async_decorator_gates_and_reports() -> None:
    """The async decorator awaits admission and reports the outcome."""
    restraint = Delay(0.0)

    @restrain("adec", restraint)
    async def work(value: int) -> int:
        return value * 2

    assert await work(21) == 42
    assert len(restraint.reported) == 1
    assert restraint.reported[0].ok
    assert restraint.releases == 1


async def test_async_decorator_reports_exceptions_and_reraises() -> None:
    """A failing call is reported, then the exception propagates."""
    restraint = Delay(0.0)

    @restrain("aexc", restraint)
    async def boom() -> None:
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        await boom()

    assert len(restraint.reported) == 1
    assert isinstance(restraint.reported[0].exception, ValueError)
    assert restraint.releases == 1


async def test_concurrent_coroutines_share_the_limit() -> None:
    """Gathered coroutines are paced rather than all admitted at once."""
    limit = Limit(second=1)
    add("ashared", limit)

    @restrain("ashared")
    async def echo() -> None:
        return None

    stop = asyncio.Event()
    heartbeat = asyncio.create_task(count_ticks(0.01, stop))

    await asyncio.gather(echo(), echo())

    stop.set()
    ticks = await heartbeat
    # Both calls completed and the loop stayed responsive while pacing them.
    assert ticks > 5, f"event loop only ran the heartbeat {ticks} times"


async def test_gate_observe_reaches_the_restraint() -> None:
    """Response signals handed to the gate arrive in the Outcome."""
    restraint = Delay(0.0)
    async with restrain("aobs", restraint) as gate:
        gate.observe(429, {"Retry-After": "7"})

    assert len(restraint.reported) == 1
    outcome = restraint.reported[0]
    assert outcome.status == 429
    assert outcome.headers == {"Retry-After": "7"}
    assert outcome.ok


async def test_sharing_one_instance_across_blocks_is_loud() -> None:
    """Re-entering a single instance would lose the first block's outcome."""
    shared = restrain("ashare", Delay(0.0))
    async with shared:
        with pytest.raises(RestraintError, match="already inside a with block"):
            async with shared:
                pass
