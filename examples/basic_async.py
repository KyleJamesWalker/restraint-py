"""Basic async example usage."""
import asyncio
import time

from restraint import restrain, Limit, add

add("foo", Limit(second=1, minute=5))


@restrain("foo")
async def echo_chamber():
    """Say the current time."""
    print(f"Hello World {time.time()}")


@restrain("foo")
async def second():
    """Say the current time."""
    print(f"Hey! {time.time()}")


async def main():
    """Process call calls in parallel."""
    await asyncio.gather(
        echo_chamber(),
        second(),
        echo_chamber(),
        echo_chamber(),
        second(),
        return_exceptions=True,
    )

    with restrain("foo"):
        print("Roll slowed")


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
