"""Test the restraint registry."""

import pytest

from restraint import Limit
from restraint.exceptions import RestraintConflictError, RestraintNotFoundError
from restraint.registry import Registry


@pytest.fixture
def registry() -> Registry:
    """An empty registry."""
    return Registry()


def test_add_then_get(registry: Registry) -> None:
    limit = Limit(second=1)
    registry.add("a", limit)
    assert registry["a"] is limit
    assert "a" in registry
    assert len(registry) == 1
    assert list(registry) == ["a"]


def test_add_is_idempotent_for_the_same_object(registry: Registry) -> None:
    limit = Limit(second=1)
    registry.add("a", limit)
    registry.add("a", limit)
    assert registry["a"] is limit


def test_add_rejects_a_conflicting_restraint(registry: Registry) -> None:
    """Silently keeping the first restraint hid real misconfiguration."""
    registry.add("a", Limit(second=1))
    with pytest.raises(RestraintConflictError, match="already registered"):
        registry.add("a", Limit(second=99))


def test_add_replaces_when_asked(registry: Registry) -> None:
    registry.add("a", Limit(second=1))
    replacement = Limit(second=99)
    registry.add("a", replacement, replace=True)
    assert registry["a"] is replacement


def test_missing_name_raises(registry: Registry) -> None:
    with pytest.raises(RestraintNotFoundError, match="nope"):
        registry["nope"]


def test_remove(registry: Registry) -> None:
    registry.add("a", Limit(second=1))
    registry.remove("a")
    assert "a" not in registry
    with pytest.raises(RestraintNotFoundError):
        registry.remove("a")


def test_clear(registry: Registry) -> None:
    registry.add("a", Limit(second=1))
    registry.add("b", Limit(second=1))
    registry.clear()
    assert len(registry) == 0
