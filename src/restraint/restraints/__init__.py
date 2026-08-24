"""Collection of various restraints."""
import datetime
import time


class Limit:
    """Simple time based limit.

    This restraint will limit the number of calls in a given time period, and
    will reset at the top of each period. This will allow to use all your
    quota as fast as possible in each given time period.

    Args:
        second: Per second rate
        minute: Per minute rate
        hour: Per hour rate
        day: Per day rate
        month: Per month rate
        year: Per year rate
        sleep_cb: Optional override sleep function, default time.sleep

    """

    def __init__(
        self,
        second=0,
        minute=0,
        hour=0,
        day=0,
        month=0,
        year=0,
        sleep_cb=None,
    ):
        """Init the restraint."""
        self.microsecond = 0
        self.second = second
        self.minute = minute
        self.hour = hour
        self.day = day
        self.month = month
        self.year = year

        self.sleep = sleep_cb or time.sleep
        self.rate_remaining = {}

        self.dt_info = datetime.datetime.now()

        if self.year:
            self.rate_remaining["year"] = self.year
        if self.month:
            self.rate_remaining["month"] = self.month
        if self.day:
            self.rate_remaining["day"] = self.day
        if self.hour:
            self.rate_remaining["hour"] = self.hour
        if self.minute:
            self.rate_remaining["minute"] = self.minute
        if self.second:
            self.rate_remaining["second"] = self.second

    def check(self, now=None):
        """Check for quota remaining."""
        now = now or datetime.datetime.now()
        quota_remaining = True
        trip = False

        test_time = datetime.datetime(year=1, month=1, day=1)
        for key in [
            "year",
            "month",
            "day",
            "hour",
            "minute",
            "second",
            "microsecond",
        ]:
            value = self.rate_remaining.get(key)
            if not trip:
                test_time = test_time.replace(**{key: getattr(self.dt_info, key)})

            if value is None:
                continue

            if trip or now > test_time + datetime.timedelta(
                **{f"{key}s": 1},
            ):
                self.rate_remaining[key] = getattr(self, key)
                if not trip:
                    trip = True
                    self.dt_info = now
            elif self.rate_remaining[key] < 1:
                quota_remaining = False

        return quota_remaining

    def _rest(self, now):
        """Rest based on quota exceeded."""
        trip = False
        replace = {}

        time_key = None
        for key in [
            "year",
            "month",
            "day",
            "hour",
            "minute",
            "second",
            "microsecond",
        ]:
            if trip:
                replace[key] = 0
            elif self.rate_remaining.get(key) == 0:
                trip = True
                time_key = f"{key}s"

        then = now.replace(**replace) + datetime.timedelta(**{time_key: 1})
        self.sleep((then - now).total_seconds())

    def gate(self):
        """Get the code."""
        now = datetime.datetime.now()

        if not self.check(now):
            self._rest(now)
            self.check()

        # Reduce quota from each category
        for key, value in self.rate_remaining.items():
            if self.rate_remaining[key] >= 1:
                self.rate_remaining[key] -= 1
