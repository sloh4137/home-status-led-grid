"""Ambient effects drawn over the boids. House power -> zaps between boids.

M3: only the rate. ZapEffect comes in M6.
"""

from math import log

ZAP_MAX_RATE = 10.0  # zaps per second at or above ZAP_MAX_WATTS


def zap_rate(w, lo, hi):
    """Zaps per second for w watts of house power: 0 at or below lo, rising
    on a log scale to ZAP_MAX_RATE at hi, so each doubling looks like a
    similar step up. w None (unavailable) -> 0. A lo of 0 counts as 1 W."""
    if w is None or w <= lo:
        return 0.0
    if w >= hi:
        return ZAP_MAX_RATE
    lo = max(lo, 1)
    # max(): with lo at 0, under 1 W would go negative
    return max(0.0, ZAP_MAX_RATE * log(w / lo) / log(hi / lo))
