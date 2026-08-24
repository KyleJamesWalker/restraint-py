"""Test the top-level restrain API."""

import pytest

import restraint
from restraint import Gate, Limit, Outcome, Reservation, Restraint, restrain


class Recorder(Restraint):
    """Admits everything and records what it is told."""

    def __init__(self) -> None:
        super().__init__()
        self.gates = 0
        self.reported: list[Outcome] = []

    def _reserve(self) -> Reservation:
        self.gates += 1
        return Reservation()

    def report(self, outcome: Outcome) -> None:
        self.reported.append(outcome)


def test_unknown_name_raises() -> None:
    with (
        pytest.raises(restraint.RestraintNotFoundError, match="not-found"),
        restrain("not-found"),
    ):
        raise RuntimeError("This should not be reached")


def test_no_name_and_no_restraint_raises() -> None:
    with pytest.raises(restraint.RestraintNotFoundError, match="Undefined restraint"):
        restrain()


def test_anonymous_restraint_needs_no_registry() -> None:
    """An unnamed restraint is usable without touching the global registry."""
    recorder = Recorder()
    with restrain(restraint=recorder):
        pass
    assert recorder.gates == 1
    assert "None" not in restraint._reg


def test_create_on_demand_registers() -> None:
    recorder = Recorder()
    with restrain("test_create_on_demand", recorder):
        pass
    assert restraint._reg["test_create_on_demand"] is recorder


def test_conflicting_registration_raises() -> None:
    restrain("conflict", Limit(second=1))
    with pytest.raises(restraint.RestraintConflictError):
        restrain("conflict", Limit(second=99))


def test_replace_overrides_a_registration() -> None:
    restrain("replaceable", Limit(second=1))
    replacement = Limit(second=99)
    restrain("replaceable", replacement, replace=True)
    assert restraint._reg["replaceable"] is replacement


def test_decorator_returns_the_wrapped_result() -> None:
    recorder = Recorder()

    @restrain("simple_decorator", recorder)
    def double(value: int) -> int:
        return value * 2

    assert double(21) == 42
    assert double(1) == 2
    assert double.__name__ == "double"
    assert recorder.gates == 2


def test_decorator_reports_exceptions_and_reraises() -> None:
    recorder = Recorder()

    @restrain("raising_decorator", recorder)
    def boom() -> None:
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        boom()
    assert isinstance(recorder.reported[0].exception, ValueError)


def test_context_manager_yields_a_gate() -> None:
    recorder = Recorder()
    with restrain("gate-cm", recorder) as gate:
        assert isinstance(gate, Gate)
    assert recorder.reported[0].ok


def test_exception_in_the_block_is_reported_and_propagates() -> None:
    recorder = Recorder()
    with pytest.raises(ValueError, match="nope"), restrain("gate-raise", recorder):
        raise ValueError("nope")
    assert isinstance(recorder.reported[0].exception, ValueError)


def test_observe_is_chainable_and_accumulates() -> None:
    recorder = Recorder()
    with restrain("gate-observe", recorder) as gate:
        gate.observe(200).observe(headers={"X-RateLimit-Remaining": "4"})
        gate.observe(retry_after=3.0)

    outcome = recorder.reported[0]
    assert outcome.status == 200
    assert outcome.headers == {"X-RateLimit-Remaining": "4"}
    assert outcome.retry_after == 3.0


def test_reusing_one_instance_across_blocks_is_loud() -> None:
    shared = restrain("gate-shared", Recorder())
    with shared:  # noqa: SIM117 - the outer block must stay open
        with pytest.raises(restraint.RestraintError, match="already inside"), shared:
            pass


def test_instance_is_reusable_sequentially() -> None:
    recorder = Recorder()
    shared = restrain("gate-sequential", recorder)
    for _ in range(3):
        with shared:
            pass
    assert len(recorder.reported) == 3
