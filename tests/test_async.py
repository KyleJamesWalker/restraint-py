"""Basic async example test."""
import asyncio
import time

from restraint import restrain, Limit, add

async_limit = Limit(second=1)
add("test_async_simple", async_limit)


@restrain("test_async_simple")
async def echo_chamber():
    """Tell the current time."""
    print(f"Hello {time.time()}")


async def process_async_calls():
    """Run all the functions in parallel."""
    await asyncio.gather(
        echo_chamber(), echo_chamber(), echo_chamber(), return_exceptions=True
    )


def test_async_restraint(when_now, mocker):
    """Test async restraint support."""
    # Remove ability to sleep
    p = mocker.patch.object(async_limit, "sleep")
    p.side_effect = lambda x: when_now.inc(x)

    sleep_spy = mocker.spy(async_limit, "sleep")

    loop = asyncio.get_event_loop()
    loop.run_until_complete(process_async_calls())

    assert sleep_spy.call_count == 2
