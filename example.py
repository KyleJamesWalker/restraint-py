"""Example usage

Questions:
    How should  I configure this? global, multiple, share, configure

"""
from restraint import limit


@limit('yt')  # todo: add and configure a name for easy use across application
def call_api(x):
    """Fake call"""
    print(x)


def main():
    """Entrypoint"""

    # Protected via function decorator
    for x in range(1, 10):
        call_api(x)

    # Context manager with explicit checks
    with limit(second=10) as l:  # if name is not passed this wouldn't be global
        for x in range(10, 16):
            l.check()
            print(f"{x} direct")

    # Use directly
    l = limit('fb')  # if name is not passed it local, else passed it's global
    l.check()
    print("direct limitation")


if __name__ == "__main__":
    main()
