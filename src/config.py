"""Settings from settings.toml, the single source of HA config on both targets.

    settings = load_settings(path)
    settings.get("HA_URL")             # None when missing
    poll_seconds(settings)             # HA_POLL_SECONDS, clamped to 1..60

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


def poll_seconds(settings):
    """HA_POLL_SECONDS as an int clamped to 1..60, or the default if unset/invalid."""
    value = settings.get("HA_POLL_SECONDS", POLL_DEFAULT)
    try:
        value = int(value)
    except (TypeError, ValueError):
        return POLL_DEFAULT
    return max(POLL_MIN, min(POLL_MAX, value))
