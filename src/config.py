"""Settings from settings.toml, the single source of HA config on both targets.

    settings = load_settings(path)
    settings.get("HA_URL")             # None when missing
    poll_seconds(settings)             # HA_POLL_SECONDS, clamped to 1..60
    persist_seconds(settings)          # PERSIST_SECONDS, clamped to 10..3600
    pond_time_scale(settings)          # POND_TIME_SCALE, clamped to 1..86400
    washer_on_watts(settings)          # WASHER_ON_WATTS, clamped to 1..500
    printer_on_watts(settings)         # PRINTER_ON_WATTS, clamped to 1..500
    zap_min_watts(settings)            # ZAP_MIN_WATTS, clamped to 0..20000
    zap_max_watts(settings)            # ZAP_MAX_WATTS, 100..50000, > the min

On CircuitPython the board's CIRCUITPY/settings.toml is read through
os.getenv() and ``path`` is ignored. On CPython the file at ``path`` is
parsed with tomllib; a missing file gives empty settings, so the desktop
falls back to FakeSensors.
"""

import os
import sys

POLL_DEFAULT = 5
POLL_MIN = 1
POLL_MAX = 60
PERSIST_DEFAULT = 60
PERSIST_MIN = 10
PERSIST_MAX = 3600
TIME_SCALE_DEFAULT = 1
TIME_SCALE_MIN = 1
TIME_SCALE_MAX = 86400  # a pond day per second
ON_WATTS_DEFAULT = 10
ON_WATTS_MIN = 1
ON_WATTS_MAX = 500
ZAP_MIN_DEFAULT = 300
ZAP_MIN_LO = 0
ZAP_MIN_HI = 20000
ZAP_MAX_DEFAULT = 5000
ZAP_MAX_LO = 100
ZAP_MAX_HI = 50000
ZAP_MIN_SPAN = 100  # ZAP_MAX_WATTS is at least this far above ZAP_MIN_WATTS


class Settings:
    """Read-only key lookup with the same ``get`` on both targets."""

    def __init__(self, values=None):
        # None means "ask os.getenv" (CircuitPython)
        self._values = values

    def get(self, key, default=None):
        if self._values is None:
            value = os.getenv(key)
        else:
            value = self._values.get(key)
        return default if value is None else value


def load_settings(path=None):
    if sys.implementation.name == "circuitpython":
        return Settings()
    import tomllib

    try:
        with open(path, "rb") as f:
            return Settings(tomllib.load(f))
    except FileNotFoundError:
        return Settings({})


def clamped_int(settings, key, default, lo, hi):
    """settings[key] as an int clamped to lo..hi, or default if unset/invalid."""
    value = settings.get(key, default)
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, value))


def poll_seconds(settings):
    """HA_POLL_SECONDS as an int clamped to 1..60, or the default if unset/invalid."""
    return clamped_int(settings, "HA_POLL_SECONDS", POLL_DEFAULT, POLL_MIN, POLL_MAX)


def persist_seconds(settings):
    """PERSIST_SECONDS: minimum seconds between state saves, clamped to 10..3600."""
    return clamped_int(
        settings, "PERSIST_SECONDS", PERSIST_DEFAULT, PERSIST_MIN, PERSIST_MAX
    )


def pond_time_scale(settings):
    """POND_TIME_SCALE: debug multiplier for the pond's aging clock, clamped
    to 1..86400 (3600 is a pond hour per second)."""
    return clamped_int(
        settings, "POND_TIME_SCALE", TIME_SCALE_DEFAULT, TIME_SCALE_MIN, TIME_SCALE_MAX
    )


def washer_on_watts(settings):
    """WASHER_ON_WATTS: above this the washer counts as running, 1..500 W."""
    return clamped_int(
        settings, "WASHER_ON_WATTS", ON_WATTS_DEFAULT, ON_WATTS_MIN, ON_WATTS_MAX
    )


def printer_on_watts(settings):
    """PRINTER_ON_WATTS: above this the 3D printer counts as on, 1..500 W."""
    return clamped_int(
        settings, "PRINTER_ON_WATTS", ON_WATTS_DEFAULT, ON_WATTS_MIN, ON_WATTS_MAX
    )


def zap_min_watts(settings):
    """ZAP_MIN_WATTS: no zaps at or below this house power, 0..20000 W."""
    return clamped_int(
        settings, "ZAP_MIN_WATTS", ZAP_MIN_DEFAULT, ZAP_MIN_LO, ZAP_MIN_HI
    )


def zap_max_watts(settings):
    """ZAP_MAX_WATTS: zaps reach their top rate at or above this, 100..50000 W.
    A max at or below ZAP_MIN_WATTS becomes min + 100."""
    hi = clamped_int(
        settings, "ZAP_MAX_WATTS", ZAP_MAX_DEFAULT, ZAP_MAX_LO, ZAP_MAX_HI
    )
    return max(hi, zap_min_watts(settings) + ZAP_MIN_SPAN)
