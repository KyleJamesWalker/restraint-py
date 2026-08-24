"""Restraint Library."""

import functools
import inspect
from importlib.metadata import PackageNotFoundError, version

from restraint.exceptions import RestraintError, RestraintNotFoundError
from restraint.registry import Registry
from restraint.restraints import Limit

try:
    __version__ = version("restraint")
except PackageNotFoundError:  # pragma: no cover - source checkout
    __version__ = "0.0.0.dev0"

_reg = Registry()
add = _reg.add


class restrain:  # noqa: N801 - public API predates the convention
    """Restraint class."""

    def __init__(self, name=None, restraint=None):
        """Restrain interaction."""
        if name is None:
            self.restraint = restraint
        elif name in _reg:
            self.restraint = _reg[name]
        elif restraint:
            self.restraint = restraint
            _reg[name] = self.restraint
        else:
            raise RestraintNotFoundError("Undefined restraint")

    async def __aenter__(self):
        """Context manager support."""
        await self.restraint.gate()
        return self

    def __enter__(self):
        """Context manager support."""
        self.restraint.gate()
        return self

    async def __aexit__(self, exception_type, exception_value, traceback):
        """Context manager support."""
        pass

    def __exit__(self, exception_type, exception_value, traceback):
        """Context manager support."""
        pass

    def __del__(self):
        """Restore original settings if object looses scope."""
        pass

    def __call__(self, org_func):
        """Add decorator Support."""
        is_async = inspect.iscoroutinefunction(org_func)

        if is_async:

            @functools.wraps(org_func)
            async def wrapper(*args, **kwargs):  # pylint: disable=C0111
                self.restraint.gate()
                return await org_func(*args, **kwargs)

            return wrapper

        @functools.wraps(org_func)
        def wrapper(*args, **kwargs):  # pylint: disable=C0111
            self.restraint.gate()
            return org_func(*args, **kwargs)

        return wrapper


__all__ = [
    "Limit",
    "RestraintError",
    "RestraintNotFoundError",
    "add",
    "restrain",
]
