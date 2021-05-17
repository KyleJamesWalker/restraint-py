"""All custom exceptions."""


class RestraintError(Exception):
    """Base exception for the library."""


class RestraintNotFoundError(RestraintError):
    """Restraint not found in registry."""
