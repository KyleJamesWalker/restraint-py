"""Basic async example usage"""
import asyncio
import time

from restraint import restrain, Limit, add

add('foo', Limit(second=1, minute=2))


@restrain('foo')
async def echo_chamber():
    print(f'Hello World {time.time()}')


@restrain('foo')
async def second():
    print(f'Hey! {time.time()}')


async def main():
    await asyncio.gather(
        echo_chamber(),
        second(),
        echo_chamber(),
        echo_chamber(),
        second(),
        return_exceptions=True
    )

    with restrain('foo'):
        print('Roll slowed')

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
