"""Basic async example test"""
import asyncio
import time

from restraint import restrain, Limit, add

async_limit = Limit(second=1)
add('test_async_simple', async_limit)


@restrain('test_async_simple')
async def echo_chamber():
    print(f'Hello {time.time()}')


async def process_async_calls():
    await asyncio.gather(
        echo_chamber(),
        echo_chamber(),
        echo_chamber(),
        return_exceptions=True
    )

def test_async_restraint(when_now, mocker):
    """Test async restraint support"""

    # Remove ability to sleep
    p = mocker.patch.object(async_limit, 'sleep')
    p.side_effect = lambda x: when_now.inc(x)

    sleep_spy = mocker.spy(async_limit, 'sleep')

    loop = asyncio.get_event_loop()
    loop.run_until_complete(process_async_calls())


import datetime
import pytest

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
