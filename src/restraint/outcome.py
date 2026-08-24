"""What happened to a gated call."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["Outcome"]


@dataclass(frozen=True, slots=True)
class Outcome:
    """The result of a call a restraint admitted.

    Adaptive restraints need to know how the server responded, which the
    library cannot discover on its own. Exceptions are reported
    automatically; status codes and headers have to be handed over with
    :meth:`restraint.Gate.observe`.

    Attributes:
        exception: The exception the call raised, if any.
        status: HTTP status code, when the caller reports one.
        headers: Response headers, when the caller reports them.
        retry_after: An explicit hold-off in seconds, overriding any
            ``Retry-After`` header.
    """

    exception: BaseException | None = None
    status: int | None = None
    headers: Mapping[str, str] | None = field(default=None)
    retry_after: float | None = None

    @property
    def ok(self) -> bool:
        """Whether the call completed without raising."""
        return self.exception is None
