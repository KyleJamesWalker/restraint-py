"""Pacing a scraper so it stays inside its budget and its welcome.

Layers a hard daily budget, an in-flight cap, a sustained rate, a jittered gap,
backoff on failure, and deference to whatever the server reports about its own
limits. Pass URLs to fetch for real (needs httpx), or run bare to watch the
pacing against a stubbed response.
"""

import sys
import time

from restraint import (
    Adaptive,
    Backoff,
    Concurrency,
    Quota,
    Spacing,
    TokenBucket,
    add,
    restrain,
)

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

polite = (
    Quota(day=10_000)  # refuse outright once the day's budget is gone
    & Concurrency(4)  # at most four requests open at a time
    & TokenBucket(rate=5)  # five a second sustained
    & Spacing(seconds=0.05, jitter=0.05)  # never bunched, never metronomic
    & Backoff(base=1.0, maximum=30.0)  # ease off when calls start failing
    & Adaptive()  # and defer to the server's own numbers
)
add("scrape", polite)

#: What a rate-limited API might report, for the no-httpx path.
STUB_HEADERS = {"X-RateLimit-Remaining": "50", "X-RateLimit-Reset": "60"}


def fetch(url: str) -> None:
    """Fetch one URL through the restraint, reporting what came back."""
    with restrain("scrape") as gate:
        started = time.monotonic()
        if httpx is None:
            # Reporting the response is what lets Adaptive and Backoff act.
            gate.observe(200, STUB_HEADERS)
            print(f"stub {url} paced to {time.monotonic() - started:.2f}s")
            return

        response = httpx.get(url, timeout=10.0)
        gate.observe(response.status_code, response.headers)
        print(f"{response.status_code} {url} in {time.monotonic() - started:.2f}s")


if __name__ == "__main__":
    targets = sys.argv[1:] or ["https://example.com"] * 10
    start = time.monotonic()
    for target in targets:
        fetch(target)
    print(f"{len(targets)} requests in {time.monotonic() - start:.2f}s")
