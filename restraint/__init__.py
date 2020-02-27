import functools
import time

class limit:
    def __init__(self, delay=1):
        """Limit interaction

        TODO:
        Support configure based on partial day (startup time), or ignore.
        Configure distribution. x calls/time, allow all at once, uniform, gitter

        """
        self.delay = delay  # TODO: convert to calls per second/minute/day/etc

    def check(self):
        """Limit check"""
        time.sleep(self.delay)

    def __enter__(self):
        """Context manager support"""
        self.check()  # Does it make sense to sleep on contruction?
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
            self.check()
            return org_func(*args, **kwargs)
        return wrapper
