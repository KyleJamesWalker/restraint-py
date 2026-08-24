# Restraint

Simple rate limit library.

```python
from restraint import restrain, Limit, add

add("example", Limit(second=1, minute=5))


@restrain("example")
def hello():
    print("Hello World")
```
