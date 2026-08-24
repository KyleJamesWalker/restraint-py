"""Restraint Library."""

from __future__ import annotations

import functools
import inspect
import threading
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any, Self

from restraint.exceptions import (
    QuotaExceededError,
    RestraintConflictError,
    RestraintError,
    RestraintNotFoundError,
)
from restraint.outcome import Outcome
from restraint.registry import Registry
from restraint.restraints import (
    Adaptive,
    Backoff,
    Composite,
    Concurrency,
    Jitter,
    Limit,
    Quota,
    Reservation,
    Restraint,
    SlidingWindow,
    Spacing,
    TokenBucket,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from types import TracebackType

try:
    __version__ = version("restraint")
except PackageNotFoundError:  # pragma: no cover - source checkout
    __version__ = "0.0.0.dev0"

_reg = Registry()
add = _reg.add


class Gate:
    """A single admitted call, and the channel for reporting how it went.

    Returned by ``with restrain(...)``. Reporting is what lets adaptive
    restraints react to the server, and the library cannot see the response
    on its own, so pass it along:

    ```python
    with restrain("api") as gate:
        response = httpx.get(url)
        gate.observe(response.status_code, response.headers)
    ```
    """

    def __init__(self, restraint: Restraint) -> None:
        """Bind a gate to the restraint that admitted the call."""
        self._restraint = restraint
        self._status: int | None = None
        self._headers: Mapping[str, str] | None = None
        self._retry_after: float | None = None

    def observe(
        self,
        status: int | None = None,
        headers: Mapping[str, str] | None = None,
        *,
        retry_after: float | None = None,
    ) -> Self:
        """Record what the server said, for restraints that adapt to it.

        Args:
            status: HTTP status code.
            headers: Response headers, read for rate-limit signals.
            retry_after: Explicit hold-off in seconds, overriding any
                ``Retry-After`` header.

        Returns:
            This gate, so the call can be chained.
        """
        if status is not None:
            self._status = status
        if headers is not None:
            self._headers = headers
        if retry_after is not None:
            self._retry_after = retry_after
        return self

    def finish(self, exception: BaseException | None = None) -> None:
        """Report the outcome to the restraint and release what it held."""
        try:
            self._restraint.report(
                Outcome(
                    exception=exception,
                    status=self._status,
                    headers=self._headers,
                    retry_after=self._retry_after,
                )
            )
        finally:
            self._restraint.release()


class restrain:  # noqa: N801 - public API predates the convention
    """Apply a restraint to a block of code or a callable.

    Works as a context manager, an async context manager, and a decorator
    over both plain and async functions:

    ```python
    add("api", Limit(second=5))

    with restrain("api"):
        ...

    async with restrain("api"):
        ...

    @restrain("api")
    def fetch(): ...
    ```

    Args:
        name: Registry key. Looked up when used alone, registered when
            given alongside ``restraint``.
        restraint: The restraint to apply. Registered under ``name`` when
            both are given.
        replace: Re-register ``name`` even if it already holds a different
            restraint.

    Raises:
        RestraintNotFoundError: ``name`` is unknown and no restraint was
            given.
        RestraintConflictError: ``name`` already holds a different restraint
            and ``replace`` is False.
    """

    def __init__(
        self,
        name: str | None = None,
        restraint: Restraint | None = None,
        *,
        replace: bool = False,
    ) -> None:
        """Resolve the restraint to apply, registering it when asked."""
        self._active: Gate | None = None
        self._active_lock = threading.Lock()
        if name is None:
            if restraint is None:
                raise RestraintNotFoundError("Undefined restraint")
            self.restraint = restraint
        elif restraint is not None:
            _reg.add(name, restraint, replace=replace)
            self.restraint = _reg[name]
        elif name in _reg:
            self.restraint = _reg[name]
        else:
            raise RestraintNotFoundError(f"Undefined restraint: {name!r}")

    def _open(self) -> Gate:
        """Claim this instance for one gated block."""
        with self._active_lock:
            if self._active is not None:
                raise RestraintError(
                    "this restrain instance is already inside a with block; "
                    "build a new one per block instead of sharing it"
                )
            self._active = Gate(self.restraint)
            return self._active

    def _abandon(self) -> None:
        """Give up a claim whose gating never completed."""
        with self._active_lock:
            self._active = None

    def _close(self, exc: BaseException | None) -> None:
        """Finish the gated block, reporting the outcome it recorded."""
        with self._active_lock:
            gate, self._active = self._active, None
        if gate is not None:
            gate.finish(exc)

    def __enter__(self) -> Gate:
        """Block until admitted, then hand back a gate for reporting."""
        # Claim before gating. Gating first would consume capacity that the
        # re-entrancy guard then refuses to hand back.
        gate = self._open()
        try:
            self.restraint.gate()
        except BaseException:
            self._abandon()
            raise
        return gate

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Report the outcome and release what the restraint held."""
        self._close(exc)

    async def __aenter__(self) -> Gate:
        """Await admission, then hand back a gate for reporting."""
        gate = self._open()
        try:
            await self.restraint.agate()
        except BaseException:
            self._abandon()
            raise
        return gate

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Report the outcome and release what the restraint held."""
        self._close(exc)

    def __call__(self, org_func: Callable[..., Any]) -> Callable[..., Any]:
        """Wrap a callable so every invocation passes through the restraint.

        Raises:
            TypeError: ``org_func`` is a generator or async generator
                function, which cannot be gated meaningfully.
        """
        if inspect.isgeneratorfunction(org_func) or inspect.isasyncgenfunction(
            org_func
        ):
            # Calling one only builds the generator; the work happens on
            # iteration, so gating here would restrain nothing and release
            # before the first item. Better to refuse than to look applied.
            raise TypeError(
                f"cannot restrain generator function {org_func.__name__!r}: "
                "gating would cover creating the generator, not consuming it. "
                "Apply the restraint inside the generator, or to the code that "
                "iterates it."
            )
        if inspect.iscoroutinefunction(org_func):

            @functools.wraps(org_func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                await self.restraint.agate()
                gate = Gate(self.restraint)
                try:
                    result = await org_func(*args, **kwargs)
                except BaseException as exc:
                    gate.finish(exc)
                    raise
                gate.finish()
                return result

            return async_wrapper

        @functools.wraps(org_func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            self.restraint.gate()
            gate = Gate(self.restraint)
            try:
                result = org_func(*args, **kwargs)
            except BaseException as exc:
                gate.finish(exc)
                raise
            gate.finish()
            return result

        return wrapper


__all__ = [
    "Adaptive",
    "Backoff",
    "Composite",
    "Concurrency",
    "Gate",
    "Jitter",
    "Limit",
    "Outcome",
    "Quota",
    "QuotaExceededError",
    "Reservation",
    "Restraint",
    "RestraintConflictError",
    "RestraintError",
    "RestraintNotFoundError",
    "SlidingWindow",
    "Spacing",
    "TokenBucket",
    "add",
    "restrain",
]
