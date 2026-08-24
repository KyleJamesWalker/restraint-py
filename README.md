# Restraint

[![CI](https://github.com/KyleJamesWalker/restraint-py/actions/workflows/ci.yml/badge.svg)](https://github.com/KyleJamesWalker/restraint-py/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/KyleJamesWalker/restraint-py/branch/main/graph/badge.svg)](https://codecov.io/gh/KyleJamesWalker/restraint-py)
[![PyPI](https://img.shields.io/pypi/v/restraint.svg)](https://pypi.org/project/restraint/)
[![Python versions](https://img.shields.io/pypi/pyversions/restraint.svg)](https://pypi.org/project/restraint/)

Composable rate limiting for Python. Restraints are small, single-purpose rules
you combine into the pacing a given API needs — hold a rate, keep a gap, cap
what is in flight, refuse once a budget is gone, and do as the server says when
it pushes back.

Works as a decorator or a context manager, sync or async, and every restraint
is safe to share across threads and coroutines.

```python
from restraint import Limit, add, restrain

add("example", Limit(second=1, minute=5))


@restrain("example")
def hello():
    print("Hello World")
```

## Install

```console
uv add restraint      # or: pip install restraint
```

Requires Python 3.11+.

## Restraints

| Restraint | Holds back when | Reach for it when |
| --- | --- | --- |
| `Limit(second=…, minute=…, …)` | The allowance for a calendar period is spent | You want to drain each window as fast as the server allows |
| `TokenBucket(rate=…, burst=…)` | No token has been earned yet | You want a smooth sustained rate with a bounded burst |
| `SlidingWindow(limit=…, per=…)` | The trailing window is full | The server counts a rolling window too |
| `Spacing(seconds=…, jitter=…)` | The last call was too recent | Calls must not bunch up, and shouldn't look metronomic |
| `Jitter(seconds=…)` | Always, by a random amount | Desynchronising a fleet of workers |
| `Concurrency(limit)` | Too many calls are already running | The cap is on calls in flight, not calls started; waiters are served in arrival order |
| `Quota(day=…, month=…)` | A hard budget is spent — **raises** | Running out is an error, not a delay |
| `Backoff(base=…)` | Recent calls failed | You should stop hammering something that is refusing you |
| `Adaptive()` | The server says so | The API reports its own rate-limit budget |

### Compose them with `&`

`a & b` builds a `Composite`, and chaining flattens rather than nesting.

One rule is rarely enough. Combine them, cheapest rejection first:

```python
from restraint import Adaptive, Quota, Spacing, TokenBucket, restrain

polite = (
    Quota(day=10_000)  # refuse once the budget is gone
    & TokenBucket(rate=5)  # hold five a second
    & Spacing(seconds=0.05, jitter=0.05)  # never bunch, never metronomic
    & Adaptive()  # then do as the server says
)

with restrain("api", polite) as gate:
    response = httpx.get(url)
    gate.observe(response.status_code, response.headers)
```

Members gate left to right and release in reverse. Order matters: a `Quota`
ahead of a `TokenBucket` refuses before a token is spent, where the reverse
wastes it.

## Usage

### Decorator, context manager, async

```python
import asyncio

from restraint import Limit, TokenBucket, add, restrain

add("api", TokenBucket(rate=5))


@restrain("api")
def fetch(url): ...


@restrain("api")
async def afetch(url): ...


with restrain("api"):
    ...


async def main():
    async with restrain("api"):
        ...
```

Async gating awaits rather than blocking, so a coroutine waiting on quota
leaves the event loop free.

### Telling a restraint how the call went

`Backoff` and `Adaptive` react to the server, which means they need to be told
what came back — the library never sees your response object. Exceptions are
reported automatically; hand over status and headers yourself:

```python
with restrain("api") as gate:
    response = httpx.get(url)
    gate.observe(response.status_code, response.headers)
```

`Adaptive` reads `X-RateLimit-Remaining` and `X-RateLimit-Reset` to spread the
budget it has left across the window it has left, and obeys `Retry-After`
outright. Without those headers it does nothing, so pair it with a configured
restraint that paces the opening calls.

A 429 or 503 with no usable headers still applies `throttle_hold` (default 1s),
since being refused is itself information.

Reset headers come in two flavours — seconds from now, or an absolute epoch
timestamp (GitHub, Reddit and X use the latter). `Adaptive` detects which per
value; force it with `reset_style="delta"` or `"epoch"` if your API is
ambiguous. Every wait it produces is bounded by `maximum` (default 300s).

### Reusing a restraint by name

`add` registers a restraint once; `restrain("name")` looks it up. Registering a
different restraint under a name already in use raises
`RestraintConflictError` — pass `replace=True` if you meant it.

```python
from restraint import Limit, add, restrain

add("shared", Limit(second=10))


@restrain("shared")
def one(): ...


@restrain("shared")
def two(): ...  # shares one budget with `one`
```

### Writing your own

Implement `_reserve`, and both the sync and async paths come for free:

```python
from restraint import Reservation, Restraint


class EveryOtherCall(Restraint):
    """Admit half the calls, delay the rest by a second."""

    def __init__(self):
        super().__init__()
        self._calls = 0

    def _reserve(self) -> Reservation:
        self._calls += 1
        if self._calls % 2:
            return Reservation()
        return Reservation(1.0, granted=True)
```

`_reserve` runs under the restraint's lock, so it can read and write its own
state freely. Return `Reservation()` to admit immediately, `Reservation(wait)`
to admit after a reserved delay, or `Reservation(wait, granted=False)` to make
the caller wait and ask again.

Three optional hooks cover the rest:

| Hook | Called | For |
| --- | --- | --- |
| `_admitted(token)` | once the reserved wait has elapsed | correcting bookkeeping with the moment the call really started, via `Reservation(..., token=...)` |
| `report(outcome)` | when the call finishes | reacting to what the server said |
| `release()` | when the call finishes | handing back anything held for its duration |

A restraint whose admission is queued rather than reserved per attempt can
override `gate` and `agate` instead — `Concurrency` and `Composite` both do.

## Caveats

- Counters live in memory. A `Quota(day=…)` refills when the process restarts,
  and separate processes each hold their own. Enforcing a limit across workers
  needs shared state, which this library does not yet have.
- `Limit` and `Quota` windows follow the system's local wall clock, so a
  daylight-saving change shifts `hour` and coarser boundaries. Everything else
  runs on a monotonic clock.
- `Concurrency` holds its slot until the gated call finishes, so it needs the
  decorator or a `with` block. A bare `gate()` requires a matching `release()`.
- Rates are targets rather than hard bounds when callers are concurrent. Waiting
  callers reserve slots up front, so one resuming late lets the next start
  slightly early. Measured worst cases: `SlidingWindow(limit=50, per=1.0)` held
  51 in a window across 16 threads, and `Spacing(seconds=0.05)` produced a 45ms
  gap across 8. The error tracks scheduler latency against your interval, so
  leave headroom on sub-second limits.

## Development

```console
make install    # sync the environment and install the git hooks
make check      # ruff, mypy, actionlint — the same hooks CI runs
make test
```

Static analysis lives in `.pre-commit-config.yaml`, and CI runs
`pre-commit run --all-files` rather than invoking each tool separately, so the
hooks and the pipeline cannot disagree. `make format` applies fixes.

## License

MIT
