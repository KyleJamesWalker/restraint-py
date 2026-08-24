"""Manage all active restraints."""


class Registry:
    """Restraint registry."""

    def __init__(self):
        """Registry of active restraints."""
        self._restraints = {}

    def __setitem__(self, name, val):
        """Set active restraint by name."""
        self._restraints[name] = val

    def __getitem__(self, name):
        """Get restraint by name."""
        return self._restraints[name]

    def __contains__(self, item):
        """Check if restraint name exists."""
        return item in self._restraints

    def add(self, name, restraint):
        """Add restraint once."""
        if name not in self:
            self._restraints[name] = restraint
