"""Fake sensor source with the same poll()/values interface as HAClient.

Used on the desktop when there is no Home Assistant config, and for
developing the readout without a network. Each interval every value takes a
small random step and stays within a plausible range.

Interface (shared with home.ha_client.HAClient):
    poll(now)      call once per frame; cheap when nothing is due
    values         {key: (state, unit, t)}; state is a string like HA's
                   ("612", "21.4", "unavailable"), t is when it was read
    last_ok        time of the last successful read, or None
    changed        set True when values change; the consumer clears it
    interval_s     seconds between reads
"""

import random

# (key, unit, start, step, low, high, format)
_SPECS = (
    ("co2", "ppm", 600.0, 25.0, 400.0, 1500.0, "%.0f"),
    ("temperature", "\u00b0C", 21.5, 0.2, 17.0, 27.0, "%.1f"),
    ("humidity", "%", 45.0, 1.5, 25.0, 75.0, "%.0f"),
)


class FakeSensors:
    def __init__(self, interval_s=5):
        self.interval_s = interval_s
        self.values = {}
        self.last_ok = None
        self.changed = False
        self._current = {spec[0]: spec[2] for spec in _SPECS}
        self._next_t = None

    def poll(self, now):
        if self._next_t is not None and now < self._next_t:
            return
        self._next_t = now + self.interval_s
        first = self.last_ok is None
        for key, unit, _, step, low, high, fmt in _SPECS:
            v = self._current[key]
            if not first:
                v = min(high, max(low, v + random.uniform(-step, step)))
                self._current[key] = v
            self.values[key] = (fmt % v, unit, now)
        self.last_ok = now
        self.changed = True
