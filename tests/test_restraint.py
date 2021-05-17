"""Test some of the top methods."""
import pytest
import restraint


def test_not_found():
    """Verify assertion on new restraints."""
    with pytest.raises(restraint.RestraintNotFoundError):
        with restraint.restrain("not-found"):
            raise RuntimeError("This should not be reached")


def test_create_on_demand():
    """Verify on demand creation."""
    with restraint.restrain("test_create_on_demand", restraint.Limit(second=1)):
        print("Success")


def test_decorator():
    """Test the decorator."""

    @restraint.restrain("simple_decorator", restraint.Limit(second=100))
    def simple_decorator():
        print("Simple")

    simple_decorator()
