"""Shared app wiring for the hardware (hardware/code.py) and desktop (run.py) runners.

Builds the scene and the text overlays on top of it. The runner owns the
display and calls ``app.tick(dt, now)`` once per frame, then refreshes.
"""

from ui.text_panel import TextPanel, panel_height

SENSOR_LINES = 3


class App:
    def __init__(self, width, height, scene_module):
        self.width = width
        self.height = height
        self.group, self._update_scene = scene_module.create_scene(width, height)

        # Sensor readout anchored to the bottom edge
        self.sensor_panel = TextPanel(
            self.group, width, height - panel_height(SENSOR_LINES), SENSOR_LINES
        )
        self.sensor_panel.set_lines(["CO2 --- PPM", "T --.-°C", "H --%"])

    def tick(self, dt, now):
        self._update_scene(dt)
