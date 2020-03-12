import calendar
import datetime
import functools
import time

from copy import deepcopy


class RestraintError(Exception):
    """The base exception for the registry"""


class RestraintNotFoundError(RestraintError):
    """Restraint not found in registry"""


class Registry:
    def __init__(self):
        """Registry of active restraints"""
        self._restraints = {}

    def get(self, name):
        if name not in self._services:
            raise RestraintNotFoundError("%s not found" % name)


class Limit:
    """Simple time based limit

    This restraint will limit the number of calls in a given time period, and
    will reset at the top of each period.   This will allow to use all your
    quota as fast as possible in each given time period.

    """
    def __init__(
        self,
        second=0, minute=0, hour=0, day=0, month=0, year=0,
    ):
        """Simple time based rate limiter

        Args:
            second: Per second rate
            minute: Per minute rate
            hour: Per hour rate
            day: Per day rate
            month: Per month rate
            year: Per year rate

        """
        self.second = second
        self.minute = minute
        self.hour = hour
        self.day = day
        self.month = month
        self.year = year
        self.dt_info = datetime.datetime.now()
        self.rate_remaining = {}

        if self.second:
            self.rate_remaining['second'] = self.second
        if self.minute:
            self.rate_remaining['minute'] = self.minute
        if self.hour:
            self.rate_remaining['hour'] = self.hour
        if self.day:
            self.rate_remaining['day'] = self.day
        if self.month:
            self.rate_remaining['month'] = self.month
        if self.year:
            self.rate_remaining['year'] = self.year


    def check(self, now=None):
        """Check for quota remaining"""
        now = now or datetime.datetime.now()
        quota_remaining = True

        for key, value in self.rate_remaining.items():
            if getattr(now, key) is not getattr(self.dt_info, key):
                self.rate_remaining[key] = getattr(self, key)
            if self.rate_remaining[key] < 1:
                quota_remaining = False

        return quota_remaining

    def sleep(self, seconds):
        """Sleep given request time"""
        time.sleep(seconds)

    def gate(self):
        now = datetime.datetime.now()

        if not self.check(now):
            # Quota has expired
            clear = False

            for key in [
                'year', 'month', 'day', 'hour',
                'minute', 'second', 'microsecond',
            ]:
                if clear:
                    then = then.replace(**{key: 0})
                elif self.rate_remaining.get(key) == 0:
                    clear = True
                    then = now.replace(**{key: getattr(now, key) + 1})

            self.sleep((then - now).total_seconds())

        # Reduce quota from each category
        for key, value in self.rate_remaining.items():
            if getattr(now, key) is not getattr(self.dt_info, key):
                self.rate_remaining[key] = getattr(self, key)
            if self.rate_remaining[key] >= 1:
                self.rate_remaining[key] -= 1


class StartupTimeAwareLimit(Limit):
    def __init__(
        self,
        second=0, minute=0, hour=0, day=0, month=0, year=0,
    ):
        """Simple rate limiter that reduces the init rate based current time

        Args:
            second: Per second rate
            minute: Per minute rate
            hour: Per hour rate
            day: Per day rate
            month: Per month rate
            year: Per year rate

        """
        super().__init__(
            second=second, minute=minute, hour=hour,
            day=day, month=month, year=year,
        )

        # This is wrong right now
        """
        62 calls a month
        means about 2 call per day in a 31 day month and 2.214 calls in a 28 mo
        31 - ((2--2.214) * cur_day_number)

        TODO: MAKE A TEST
        """
        cur_month_days = calendar.monthrange(
            self.dt_info.year, self.dt_info.month
        )[1]
        cur_year_days = 366 if calendar.isleap(self.dt_info.year) else 365
        self.rate_remaining = {
            'second': int(
                self.second * (self.dt_info.microsecond / 1000000) + 1
                ),
            'minute': int(self.minute * (self.dt_info.second / 60) + 1),
            'hour': int(self.hour * (self.dt_info.minute / 60) + 1),
            'day': int(self.day * (self.dt_info.hour / 24) + 1),
            'month': int(
                self.month * (self.dt_info.day / cur_month_days) + 1
            ),
            'year': int(
                self.year * (
                    self.dt_info.timetuple().tm_yday / cur_year_days
                ) + 1
            ),
        }



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
