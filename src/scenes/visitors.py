"""Visitors: creatures Home Assistant calls into the pond.

Each visitor has a condition on the sensor values (the washer's or the 3D
printer's plug drawing more than its on threshold). It arrives as soon as the
condition is true, but leaves only after the condition has been false for its
off delay, which rides over a washer's soaks and pauses and a printer's heater
cycling. The timer runs on the scene's real dt, not on poll times, so it keeps
counting while HA is quiet; unavailable counts as false, so a dead sensor
makes the visitor leave after the delay instead of staying forever.

Visitors are never persisted, never age and never breed: after a restart a
running washer brings its visitor back on the first poll.

M3: the conditions and timers only. Arrive/leave print on the console; the
creatures come in later milestones.
"""

from config import printer_on_watts, washer_on_watts

WASHER_OFF_SECONDS = 300
PRINTER_OFF_SECONDS = 60


def watts(entry):
    """The entry's state as a float, or None if missing or not a number
    ("unavailable", "unknown")."""
    if entry is None:
        return None
    try:
        return float(entry[0])
    except (TypeError, ValueError):
        return None


def above(entry, on_watts):
    """True when watts(entry) is above on_watts. No number -> False."""
    w = watts(entry)
    return w is not None and w > on_watts


def power_above(key, on_watts):
    """A condition(values): the ``key`` entry draws more than on_watts."""

    def condition(values):
        return above(values.get(key), on_watts)

    return condition


class Visitor:
    """name, condition(values) -> bool, off_seconds."""

    def __init__(self, name, condition, off_seconds):
        self.name = name
        self.condition = condition
        self.off_seconds = off_seconds
        self.present = False
        self._wanted = False  # the condition at the last set_sensors
        self._off_for = 0.0  # seconds the condition has been false while present

    def set_sensors(self, values):
        self._wanted = self.condition(values)
        if self._wanted:
            self._off_for = 0.0
            if not self.present:
                self.present = True
                print("visitor: %s arrive" % self.name)

    def tick(self, dt):
        if not self.present or self._wanted:
            return
        self._off_for += dt
        if self._off_for >= self.off_seconds:
            self.present = False
            self._off_for = 0.0
            print("visitor: %s leave" % self.name)


def visitors_from(config):
    """The pond's visitors, with thresholds from settings.toml (config.Settings)."""
    return (
        Visitor(
            "eel",
            power_above("washer_power", washer_on_watts(config)),
            WASHER_OFF_SECONDS,
        ),
        Visitor(
            "lily",
            power_above("printer_power", printer_on_watts(config)),
            PRINTER_OFF_SECONDS,
        ),
    )


class Visitors:
    """All visitors: ``set_sensors(values)`` on every sensor change,
    ``tick_timers(dt)`` every frame (and while the display sleeps)."""

    def __init__(self, visitors):
        self.visitors = visitors

    def set_sensors(self, values):
        for v in self.visitors:
            v.set_sensors(values)

    def tick_timers(self, dt):
        for v in self.visitors:
            v.tick(dt)
