import datetime
import pytest

from restraint import Limit


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
        base_time = datetime.datetime(2020, 1, 15, 7, 9, 32, 313375)

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

    monkeypatch.setattr('datetime.datetime', MockedDatetime)

    yield MockedDatetime


def test_seconds(when_now, mocker):
    """Test simple second limit"""
    l = Limit(second=3)
    # Remove ability to sleep
    p = mocker.patch.object(l, 'sleep')
    p.side_effect = lambda x: print(x)

    spy = mocker.spy(l, 'sleep')

    # First three calls should work
    l.gate()
    l.gate()
    l.gate()
    spy.assert_not_called()

    # Last call should hit the gate
    l.gate()
    spy.assert_called_once_with(0.686625)


def test_minutes(when_now, mocker):
    """Test seconds and minutes limit"""
    l = Limit(second=1, minute=3)

    # Remove ability to sleep
    p = mocker.patch.object(l, 'sleep')
    p.side_effect = lambda x: print(x)

    spy = mocker.spy(l, 'sleep')

    # First  call should work
    l.gate()
    spy.assert_not_called()

    # Second call should block the seconds
    l.gate()
    assert spy.mock_calls == [mocker.call(0.686625)]

    # Advance time to allow next call without gate
    when_now.offset_seconds+= 1
    l.gate()
    assert spy.mock_calls == [mocker.call(0.686625)]

    # Allow seconds, but hit  minute gate
    when_now.offset_seconds += 1
    l.gate()
    assert spy.mock_calls == [mocker.call(0.686625), mocker.call(25.686625)]

    # Advance to next minute
    when_now.offset_seconds += 26
    l.gate()
    assert spy.mock_calls == [mocker.call(0.686625), mocker.call(25.686625)]
