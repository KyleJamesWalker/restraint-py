"""Basic async example usage."""

import asyncio
import time

from restraint import Limit, add, restrain

add("foo", Limit(second=1, minute=5))


@restrain("foo")
async def echo_chamber() -> None:
    """Say the current time."""
    print(f"Hello World {time.time()}")


@restrain("foo")
async def second() -> None:
    """Say the current time."""
    print(f"Hey! {time.time()}")


async def main() -> None:
    """Process all calls concurrently."""
    await asyncio.gather(
        echo_chamber(),
        second(),
        echo_chamber(),
        echo_chamber(),
        second(),
    )

    async with restrain("foo"):
        print("Roll slowed")


if __name__ == "__main__":
    asyncio.run(main())
