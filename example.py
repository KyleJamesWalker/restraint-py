"""Example usage

Questions:
    How should  I configure this? global, multiple, share, configure

"""
import time

from restraint import restrain, Limit


@restrain('foo', Limit(second=1, minute=5))
def echo_chamber():
    print(f'Hello World {time.time()}\n\n')


echo_chamber()
echo_chamber()
echo_chamber()
echo_chamber()
echo_chamber()
