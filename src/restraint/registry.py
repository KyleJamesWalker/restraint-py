"""Manage all active restraints."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from restraint.exceptions import RestraintConflictError, RestraintNotFoundError

if TYPE_CHECKING:
    from collections.abc import Iterator

    from restraint.restraints import Restraint

__all__ = ["Registry"]


class Registry:
    """Restraint registry keyed by name."""

    def __init__(self) -> None:
        """Registry of active restraints."""
        self._restraints: dict[str, Restraint] = {}
        self._lock = threading.RLock()

    def __setitem__(self, name: str, val: Restraint) -> None:
        """Set active restraint by name, replacing any existing entry."""
        with self._lock:
            self._restraints[name] = val

    def __getitem__(self, name: str) -> Restraint:
        """Get restraint by name.

        Raises:
            RestraintNotFoundError: No restraint is registered under ``name``.
        """
        with self._lock:
            try:
                return self._restraints[name]
            except KeyError:
                raise RestraintNotFoundError(f"Undefined restraint: {name!r}") from None

    def __contains__(self, item: object) -> bool:
        """Check if restraint name exists."""
        with self._lock:
            return item in self._restraints

    def __iter__(self) -> Iterator[str]:
        """Iterate over the registered names."""
        with self._lock:
            return iter(tuple(self._restraints))

    def __len__(self) -> int:
        """Return how many restraints are registered."""
        with self._lock:
            return len(self._restraints)

    def add(self, name: str, restraint: Restraint, *, replace: bool = False) -> None:
        """Register a restraint under ``name``.

        Args:
            name: Registry key.
            restraint: The restraint to register.
            replace: Overwrite an existing, different restraint.

        Raises:
            RestraintConflictError: ``name`` already holds a different
                restraint and ``replace`` is False. Registering the same
                object twice is idempotent and never raises.
        """
        with self._lock:
            existing = self._restraints.get(name)
            if existing is not None and existing is not restraint and not replace:
                raise RestraintConflictError(
                    f"{name!r} is already registered; pass replace=True to override"
                )
            self._restraints[name] = restraint

    def remove(self, name: str) -> None:
        """Unregister ``name``.

        Raises:
            RestraintNotFoundError: No restraint is registered under ``name``.
        """
        with self._lock:
            if self._restraints.pop(name, None) is None:
                raise RestraintNotFoundError(f"Undefined restraint: {name!r}")

    def clear(self) -> None:
        """Drop every registered restraint."""
        with self._lock:
            self._restraints.clear()
