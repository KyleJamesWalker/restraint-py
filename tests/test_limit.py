"""Test simple limit"""
from restraint import Limit


def test_seconds(when_now, mocker):
    """Test simple second limit"""
    lmt = Limit(second=3)
    # Remove ability to sleep
    p = mocker.patch.object(lmt, 'sleep')
    p.side_effect = lambda x: when_now.inc(x)

    spy = mocker.spy(lmt, 'sleep')

    # First three calls should work
    lmt.gate()
    lmt.gate()
    lmt.gate()
    spy.assert_not_called()

    # Last call should hit the gate
    lmt.gate()
    spy.assert_called_once_with(0.686625)


def test_minutes(when_now, mocker):
    """Test seconds and minutes limit"""
    lmt = Limit(second=1, minute=3)

    # Remove ability to sleep
    p = mocker.patch.object(lmt, 'sleep')
    # Sleep for a tiny bit longer so show time
    # passing between test calls
    p.side_effect = lambda x: when_now.inc(x + .0001)

    spy = mocker.spy(lmt, 'sleep')
    calls = []

    # First call no sleep
    lmt.gate()
    assert spy.mock_calls == calls

    # Second expired expect rest till next second
    lmt.gate()
    calls.append(mocker.call(0.686625))
    assert spy.mock_calls == calls

    # Last call waited and used the only quota, rest till next second
    lmt.gate()
    calls.append(mocker.call(0.9999))
    assert spy.mock_calls == calls

    # Out of mins, once finished use all second quota
    lmt.gate()
    calls.append(mocker.call(56.9999))
    assert spy.mock_calls == calls

    # Same as before
    lmt.gate()
    calls.append(mocker.call(0.9999))
    assert spy.mock_calls == calls

    # Same as it ever was
    lmt.gate()
    calls.append(mocker.call(0.9999))
    assert spy.mock_calls == calls

    # Out of minutes
    lmt.gate()
    calls.append(mocker.call(57.9999))
    assert spy.mock_calls == calls
