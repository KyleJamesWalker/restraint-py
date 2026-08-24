"""All custom exceptions."""


class RestraintError(Exception):
    """Base exception for the library."""


class RestraintNotFoundError(RestraintError):
    """Restraint not found in registry."""


class RestraintConflictError(RestraintError):
    """A different restraint is already registered under this name."""


class QuotaExceededError(RestraintError):
    """A hard quota is spent and the caller asked not to wait for it."""
