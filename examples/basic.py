"""Basic example usage"""
import time

from restraint import restrain, Limit, add

add('foo', Limit(second=1, minute=5))


@restrain('foo')
def echo_chamber():
    print(f'Hello World {time.time()}')


@restrain('foo')
def second():
    print(f'Hey! {time.time()}')


echo_chamber()
second()
echo_chamber()
echo_chamber()
second()

with restrain('foo'):
    print('Roll slowed')
