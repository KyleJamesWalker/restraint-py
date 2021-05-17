"""Global test fixtures"""
import datetime
import pytest


@pytest.fixture
def when_now(monkeypatch):
    """Fixture to easily set the time"""

    class MockedDatetime(datetime.datetime):
        """Change current time"""

        offset_months = 0
        offset_days = 0
        offset_hours = 0
        offset_minutes = 0
        offset_seconds = 0
        offset_microseconds = 0
        base_time = datetime.datetime(2020, 1, 15, 7, 9, 1, 313375)

        @classmethod
        def inc(cls, seconds):
            cls.offset_seconds += seconds

        @classmethod
        def now(cls):
            """Fake datetime.now()"""
            cur_time = cls.base_time + datetime.timedelta(
                days=cls.offset_days,
                hours=cls.offset_hours,
                minutes=cls.offset_minutes,
                seconds=cls.offset_seconds,
                microseconds=cls.offset_microseconds,
            )
            return cur_time

        @classmethod
        def utcnow(cls):
            """Fake datetime.now()"""
            return cls.now()

    monkeypatch.setattr("datetime.datetime", MockedDatetime)

    yield MockedDatetime
