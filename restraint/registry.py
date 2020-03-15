"""Manage all active restraints"""


class Registry:
    def __init__(self):
        """Registry of active restraints"""
        self._restraints = {}

    def __setitem__(self, name, val):
        self._restraints[name] = val

    def __getitem__(self, name):
        return self._restraints[name]

    def __contains__(self, item):
        return item in self._restraints

    def add(self, name, restraint):
        """Add restraint once"""
        if name not in self:
            self._restraints[name] = restraint
