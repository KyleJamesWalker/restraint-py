"""Restraint Library"""
import functools

from restraint.exceptions import RestraintError, RestraintNotFoundError
from restraint.registry import Registry
from restraint.restraints import Limit

_reg = Registry()
add = _reg.add


class restrain:
    def __init__(self, name=None, restraint=None):
        """Restrain interaction"""
        if name is None:
            self.restraint = restraint
        elif name in _reg:
            self.restraint = _reg[name]
        elif restraint:
            self.restraint = restraint
            _reg[name] = self.restraint
        else:
            raise RestraintNotFoundError('Undefined restraint')

    def __enter__(self):
        """Context manager support"""
        self.restraint.gate()
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        """Context manager support"""
        pass

    def __del__(self):
        """Restore original settings if object looses scope. """
        pass

    def __call__(self, org_func):
        """Decorator Support"""
        @functools.wraps(org_func)
        def wrapper(*args, **kwargs):  # pylint: disable=C0111
            self.restraint.gate()
            return org_func(*args, **kwargs)
        return wrapper


__all__ = [
    'RestraintError',
    'RestraintNotFoundError',
    'add',
    'restrain',
    'Limit',
]
