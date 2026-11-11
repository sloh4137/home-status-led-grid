"""Shared app wiring for the hardware (hardware/code.py) and desktop (run.py) runners.

Builds the scene and the text overlays on top of it. The runner owns the
display and calls ``app.tick(dt, now)`` once per frame, then refreshes.

``sensors`` is anything with the poll(now) / values / last_ok / changed /
interval_s interface (home.fake_sensors.FakeSensors, home.ha_client.HAClient,
or home.no_sensors.NoSensors for a status message like NO WIFI).

``buttons`` is anything with poll(now) -> gestures (ui.buttons.KeypadButtons,
SimButtons or NoButtons). The gestures drive the menu at the top of the screen.
"""

from home.readout import sensor_lines, status_message
from ui.buttons import NoButtons
from ui.menu import Menu
from ui.text_panel import TextPanel, panel_height

SENSOR_LINES = 3


class App:
    def __init__(self, width, height, scene_module, sensors, now, buttons=None):
        self.width = width
        self.height = height
        self.buttons = buttons or NoButtons()
        self.group, self._update_scene = scene_module.create_scene(width, height)
        # Sensor readout anchored to the bottom edge
        self.sensor_panel = TextPanel(
            self.group, width, height - panel_height(SENSOR_LINES), SENSOR_LINES
        )
        self.set_sensors(sensors, now)

        self.sensors_on = True
        self.menu = Menu(
            [
                (self._sensors_label, self._toggle_sensors),
                (lambda: "HIDE MENU", self._hide_menu),
            ]
        )
        # Menu on top of everything, anchored to the top edge; hidden until
        # the first button press
        self.menu_panel = TextPanel(self.group, width, 0, len(self.menu.items))
        self.menu_panel.hidden = True

    # ------------------------------------------------------------ menu items
    def _sensors_label(self):
        return "SENSORS ON" if self.sensors_on else "SENSORS OFF"

    def _toggle_sensors(self):
        self.sensors_on = not self.sensors_on
        self.sensor_panel.hidden = not self.sensors_on

    def _hide_menu(self):
        self.menu.hide()

    def _update_menu(self, now):
        menu = self.menu
        redraw = False
        for gesture in self.buttons.poll(now):
            redraw = menu.handle(gesture) or redraw
        if not redraw:
            return
        if menu.visible:
            # set_lines skips the redraw when nothing changed
            self.menu_panel.set_lines(menu.lines(), menu.index)
        if self.menu_panel.hidden == menu.visible:
            self.menu_panel.hidden = not menu.visible

    def set_sensors(self, sensors, now):
        """Swap the sensor source, e.g. once WiFi is up at boot."""
        self.sensors = sensors
        self._started = now
        self._message = status_message(sensors, now, now)
        self.sensor_panel.set_lines(sensor_lines(sensors.values, self._message))

    def tick(self, dt, now):
        self._update_menu(now)
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
