"""Collection of various restraints."""

from restraint.restraints.adaptive import Adaptive
from restraint.restraints.backoff import Backoff
from restraint.restraints.base import Reservation, Restraint
from restraint.restraints.bucket import TokenBucket
from restraint.restraints.composite import Composite
from restraint.restraints.concurrency import Concurrency
from restraint.restraints.limit import Limit
from restraint.restraints.quota import Quota
from restraint.restraints.spacing import Jitter, Spacing
from restraint.restraints.window import SlidingWindow

__all__ = [
    "Adaptive",
    "Backoff",
    "Composite",
    "Concurrency",
    "Jitter",
    "Limit",
    "Quota",
    "Reservation",
    "Restraint",
    "SlidingWindow",
    "Spacing",
    "TokenBucket",
]
