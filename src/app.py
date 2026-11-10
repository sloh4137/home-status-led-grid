"""Shared app wiring for the hardware (hardware/code.py) and desktop (run.py) runners.

Builds the scene and the text overlays on top of it. The runner owns the
display and calls ``app.tick(dt, now)`` once per frame, then refreshes.

``sensors`` is anything with the poll(now) / values / last_ok / changed /
interval_s interface (home.fake_sensors.FakeSensors, home.ha_client.HAClient,
or home.no_sensors.NoSensors for a status message like NO WIFI).
"""

from home.readout import sensor_lines, status_message
from ui.text_panel import TextPanel, panel_height

SENSOR_LINES = 3


class App:
    def __init__(self, width, height, scene_module, sensors, now):
        self.width = width
        self.height = height
        self.group, self._update_scene = scene_module.create_scene(width, height)
        # Sensor readout anchored to the bottom edge
        self.sensor_panel = TextPanel(
            self.group, width, height - panel_height(SENSOR_LINES), SENSOR_LINES
        )
        self.set_sensors(sensors, now)

    def set_sensors(self, sensors, now):
        """Swap the sensor source, e.g. once WiFi is up at boot."""
        self.sensors = sensors
        self._started = now
        self._message = status_message(sensors, now, now)
        self.sensor_panel.set_lines(sensor_lines(sensors.values, self._message))

    def tick(self, dt, now):
        sensors = self.sensors
        sensors.poll(now)
        message = status_message(sensors, now, self._started)
        # Only build strings when something changed; set_lines also skips
        # redrawing when the text comes out the same.
        if sensors.changed or message != self._message:
            sensors.changed = False
            self._message = message
            self.sensor_panel.set_lines(sensor_lines(sensors.values, message))
        self._update_scene(dt)
