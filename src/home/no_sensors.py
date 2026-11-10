"""Placeholder sensor source that only shows a status message.

Used on hardware while WiFi connects and when there is no way to read HA
(NO WIFI, NO HA CFG). Same interface as FakeSensors / HAClient, plus
``message``, which the readout shows instead of values.
"""


class NoSensors:
    def __init__(self, message):
        self.message = message
        self.values = {}
        self.last_ok = None
        self.changed = False
        self.interval_s = 60

    def poll(self, now):
        pass
