"""Fake sensor source with the same poll()/values interface as HAClient.

Used on the desktop when there is no Home Assistant config, and for
developing the readout without a network. Each interval every value takes a
small random step and stays within a plausible range. CO2 instead sweeps
slowly between its low and high (with the random step as jitter), so the
simulator shows the CO2 saturation shift in a few minutes.

The pond's HA effects get fakes too, cycling slowly so a headless run shows
each one: the washer's and the 3D printer's plug power (on for part of each
cycle, with dips under the on threshold while the washer runs) and the
house's total power (a sweep like CO2's). ``display`` is "on".

On the desktop, ``key(keysym)`` takes simulator keys (run.py passes them on),
each updating the values at once:
    + / -   set CO2 by hand in CO2_KEY_STEP ppm steps (stops its sweep)
    W / P   toggle the washer / the printer (stops its cycle)
    [ / ]   set the total power by hand in POWER_KEY_STEP W steps (stops its sweep)
    D       toggle the display helper between "on" and "off"
    0       resume every cycle and sweep

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

# Plug power: (key, cycle period s, seconds on per cycle, off W range, on W range)
_PLUGS = (
    # The washer is off longer than WASHER_OFF_SECONDS (300), so the eel leaves
    ("washer_power", 600, 120, (0.0, 8.0), (20.0, 500.0)),
    ("printer_power", 240, 90, (3.0, 6.0), (80.0, 250.0)),
)
# Share of the washer's "on" reads that dip under 10 W, like a soak or pause
WASHER_DIP_CHANCE = 0.15
_PLUG_KEYS = {"w": "washer_power", "W": "washer_power",
              "p": "printer_power", "P": "printer_power"}

# Total house power: sweeps from low to high and back every period
TOTAL_LOW = 150.0
TOTAL_HIGH = 6000.0
TOTAL_PERIOD = 300
POWER_KEY_STEP = 500
_POWER_KEYS = {"bracketleft": -POWER_KEY_STEP, "bracketright": POWER_KEY_STEP}
_DISPLAY_KEYS = ("d", "D")


class FakeSensors:
    def __init__(self, interval_s=5):
        self.interval_s = interval_s
        self.values = {}
        self.last_ok = None
        self.changed = False
        self._current = {spec[0]: spec[2] for spec in _SPECS}
        self._current["total_power"] = TOTAL_LOW
        self._plug_on = {}  # plug key -> on in the latest read
        self._display = "on"
        self._next_t = None
        self._started = None
        self._manual = {}  # key -> value set by hand, overrides the sweep

    def key(self, keysym):
        """Simulator key, see the module docstring. Other keys are ignored."""
        manual = self._manual
        if keysym in _SWEEP_KEYS:
            manual.clear()
        elif keysym in _PLUG_KEYS:
            key = _PLUG_KEYS[keysym]
            manual[key] = not manual.get(key, self._plug_on.get(key, False))
            print("fake: %s %s" % (key, "on" if manual[key] else "off"))
        elif keysym in _POWER_KEYS:
            v = manual.get("total_power", self._current["total_power"])
            v = round(v / POWER_KEY_STEP) * POWER_KEY_STEP + _POWER_KEYS[keysym]
            manual["total_power"] = min(20000.0, max(0.0, v))
            print("fake: total_power %.0f W" % manual["total_power"])
        elif keysym in _DISPLAY_KEYS:
            self._display = "off" if self._display == "on" else "on"
            print("fake: display %s" % self._display)
        else:
            delta = _CO2_KEYS.get(keysym)
            if delta is None:
                return
            # Start from the shown value, rounded to the step
            v = manual.get("co2", self._current["co2"])
            v = round(v / CO2_KEY_STEP) * CO2_KEY_STEP + delta
            manual["co2"] = min(3000.0, max(0.0, v))
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
        self._poll_power(now - self._started)
        self.values["display"] = (self._display, None, now)
        self.last_ok = now
        self.changed = True

    def _poll_power(self, elapsed):
        now = elapsed + self._started
        manual = self._manual
        for key, period, on_s, off_range, on_range in _PLUGS:
            on = manual.get(key)
            if on is None:
                on = elapsed % period < on_s
            self._plug_on[key] = on
            if not on:
                w = random.uniform(*off_range)
            elif key == "washer_power" and random.random() < WASHER_DIP_CHANCE:
                w = random.uniform(2.0, 9.0)
            else:
                w = random.uniform(*on_range)
            self.values[key] = ("%.1f" % w, "W", now)
        v = manual.get("total_power")
        if v is None:
            phase = 2 * pi * elapsed / TOTAL_PERIOD
            v = TOTAL_LOW + (TOTAL_HIGH - TOTAL_LOW) * (1 - cos(phase)) / 2
        self._current["total_power"] = v
        self.values["total_power"] = ("%.0f" % v, "W", now)
