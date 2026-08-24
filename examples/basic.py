"""Basic example usage."""

import time

from restraint import Limit, add, restrain

add("foo", Limit(second=1, minute=5))


@restrain("foo")
def echo_chamber() -> None:
    """Say the current time."""
    print(f"Hello World {time.time()}")


@restrain("foo")
def second() -> None:
    """Say the current time."""
    print(f"Hey! {time.time()}")


if __name__ == "__main__":
    echo_chamber()
    second()
    echo_chamber()
    echo_chamber()
    second()

    with restrain("foo"):
        print("Roll slowed")
