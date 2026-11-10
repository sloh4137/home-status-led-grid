"""Shared app wiring for the hardware (hardware/code.py) and desktop (run.py) runners.

Builds the scene and the text overlays on top of it. The runner owns the
display and calls ``app.tick(dt, now)`` once per frame, then refreshes.

``sensors`` is anything with the poll(now) / values / last_ok / changed /
interval_s interface (home.fake_sensors.FakeSensors, later HAClient).
"""

from home.readout import is_offline, sensor_lines
from ui.text_panel import TextPanel, panel_height

SENSOR_LINES = 3


class App:
    def __init__(self, width, height, scene_module, sensors, now):
        self.width = width
        self.height = height
        self.group, self._update_scene = scene_module.create_scene(width, height)
        self.sensors = sensors
        self._started = now
        self._offline = False

        # Sensor readout anchored to the bottom edge
        self.sensor_panel = TextPanel(
            self.group, width, height - panel_height(SENSOR_LINES), SENSOR_LINES
        )
        self.sensor_panel.set_lines(sensor_lines(sensors.values))

    def tick(self, dt, now):
        sensors = self.sensors
        sensors.poll(now)
        offline = is_offline(sensors, now, self._started)
        # Only build strings when something changed; set_lines also skips
        # redrawing when the text comes out the same.
        if sensors.changed or offline != self._offline:
            sensors.changed = False
            self._offline = offline
            self.sensor_panel.set_lines(sensor_lines(sensors.values, offline))
        self._update_scene(dt)
