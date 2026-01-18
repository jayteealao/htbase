"""Tail sampling logic for wide events.

Implements intelligent sampling that keeps 100% of errors, slow requests,
and important traffic while sampling the rest.
"""

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .events import WideEvent, Outcome

# Sampling configuration (can be overridden via environment variables)
SLOW_REQUEST_THRESHOLD_MS = 2000  # Keep requests slower than this
RANDOM_SAMPLE_RATE = 0.05  # Keep 5% of normal traffic
VIP_TIERS = {"premium", "enterprise"}  # Always keep these user tiers


def should_sample(event: "WideEvent") -> bool:
    """Determine if a wide event should be logged based on tail sampling.

    Sampling strategy:
    - ALWAYS keep errors (100%)
    - ALWAYS keep slow requests (duration > threshold)
    - ALWAYS keep VIP users (premium/enterprise tiers)
    - RANDOMLY sample the rest (configured rate)

    Args:
        event: The wide event to evaluate

    Returns:
        True if the event should be logged, False otherwise
    """
    from .events import Outcome

    # ALWAYS keep errors
    if event.outcome == Outcome.ERROR:
        return True

    # ALWAYS keep error events (has error field)
    if event.error is not None:
        return True

    # ALWAYS keep slow requests
    if event.duration_ms is not None and event.duration_ms > SLOW_REQUEST_THRESHOLD_MS:
        return True

    # Check for VIP user tier (API requests only)
    if hasattr(event, "auth") and event.auth is not None:
        if event.auth.tier in VIP_TIERS:
            return True

    # Check for feature flags (if we add them later)
    # This would be: if event.feature_flags: return True

    # Randomly sample the rest
    return random.random() < RANDOM_SAMPLE_RATE


def configure_sampling(
    slow_threshold_ms: int = 2000,
    sample_rate: float = 0.05,
    vip_tiers: set = None,
) -> None:
    """Configure tail sampling parameters.

    Args:
        slow_threshold_ms: Threshold for slow requests (default: 2000ms)
        sample_rate: Random sampling rate for normal traffic (default: 0.05 = 5%)
        vip_tiers: Set of tier names to always keep (default: {"premium", "enterprise"})
    """
    global SLOW_REQUEST_THRESHOLD_MS, RANDOM_SAMPLE_RATE, VIP_TIERS

    SLOW_REQUEST_THRESHOLD_MS = slow_threshold_ms
    RANDOM_SAMPLE_RATE = sample_rate

    if vip_tiers is not None:
        VIP_TIERS = vip_tiers
