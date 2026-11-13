"""Fake sensor source with the same poll()/values interface as HAClient.

Used on the desktop when there is no Home Assistant config, and for
developing the readout without a network. Each interval every value takes a
small random step and stays within a plausible range. CO2 instead sweeps
slowly between its low and high (with the random step as jitter), so the
simulator shows the CO2 brightness shift in a few minutes.

On the desktop, ``key(keysym)`` takes simulator keys (run.py passes them on):
+ / - set CO2 by hand in CO2_KEY_STEP ppm steps, which stops the sweep and
updates the values at once; 0 goes back to the sweep.

Interface (shared with home.ha_client.HAClient):
    poll(now)      call once per frame; cheap when nothing is due
    values         {key: (state, unit, t)}; state is a string like HA's
                   ("612", "21.4", "unavailable"), t is when it was read
    last_ok        time of the last successful read, or None
    changed        set True when values change; the consumer clears it
    interval_s     seconds between reads
"""

import random
from math import cos, pi

# (key, unit, start, step, low, high, format, sweep period in s or None)
_SPECS = (
    ("co2", "ppm", 400.0, 25.0, 400.0, 2200.0, "%.0f", 240),
    ("temperature", "\u00b0C", 21.5, 0.2, 17.0, 27.0, "%.1f", None),
    ("humidity", "%", 45.0, 1.5, 25.0, 75.0, "%.0f", None),
)

CO2_KEY_STEP = 100
_CO2_KEYS = {
    "plus": CO2_KEY_STEP,
    "equal": CO2_KEY_STEP,  # + without shift
    "KP_Add": CO2_KEY_STEP,
    "minus": -CO2_KEY_STEP,
    "KP_Subtract": -CO2_KEY_STEP,
}
_SWEEP_KEYS = ("0", "KP_0")


class FakeSensors:
    def __init__(self, interval_s=5):
        self.interval_s = interval_s
        self.values = {}
        self.last_ok = None
        self.changed = False
        self._current = {spec[0]: spec[2] for spec in _SPECS}
        self._next_t = None
        self._started = None
        self._manual = {}  # key -> value set by hand, overrides the sweep

    def key(self, keysym):
        """Simulator key: + / - set CO2 by hand, 0 resumes the sweep."""
        if keysym in _SWEEP_KEYS:
            self._manual.pop("co2", None)
        else:
            delta = _CO2_KEYS.get(keysym)
            if delta is None:
                return
            # Start from the shown value, rounded to the step
            v = self._manual.get("co2", self._current["co2"])
            v = round(v / CO2_KEY_STEP) * CO2_KEY_STEP + delta
            self._manual["co2"] = min(3000.0, max(0.0, v))
        self._next_t = None  # read again on the next poll

    def poll(self, now):
        if self._next_t is not None and now < self._next_t:
            return
        self._next_t = now + self.interval_s
        first = self.last_ok is None
        if first:
            self._started = now
        for key, unit, _, step, low, high, fmt, period in _SPECS:
            v = self._current[key]
            if key in self._manual:
                v = self._current[key] = self._manual[key]
            elif period:
                # Starts at low, peaks at high half a period later
                phase = 2 * pi * (now - self._started) / period
                v = low + (high - low) * (1 - cos(phase)) / 2
                if not first:
                    v += random.uniform(-step, step)
                v = min(high, max(low, v))
                self._current[key] = v
            elif not first:
                v = min(high, max(low, v + random.uniform(-step, step)))
                self._current[key] = v
            self.values[key] = (fmt % v, unit, now)
        self.last_ok = now
        self.changed = True
