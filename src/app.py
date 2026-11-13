"""Shared app wiring for the hardware (hardware/code.py) and desktop (run.py) runners.

Builds the scene and the text overlays on top of it. The runner owns the
display and calls ``app.tick(dt, now)`` once per frame, then refreshes.

``sensors`` is anything with the poll(now) / values / last_ok / changed /
interval_s interface (home.fake_sensors.FakeSensors, home.ha_client.HAClient,
or home.no_sensors.NoSensors for a status message like NO WIFI).

``buttons`` is anything with poll(now) -> gestures (ui.buttons.KeypadButtons,
SimButtons or NoButtons). The gestures drive the menu at the top of the screen.

``set_rotation(degrees)`` is called by the ROTATE 90 menu item with 0, 90,
180 or 270: display.rotation on hardware, VirtualDisplay.rotation on the
desktop. The whole group rotates, so the text panels turn with the scene.

``store`` (persist.store.Store, optional) holds the saved menu settings: they
are loaded and applied here, menu actions mark the store dirty, and
``tick`` lets it save at most once per PERSIST_SECONDS. The DUMP STATE menu
item prints the document on the console, and a ``store.notice`` from loading
(BAD STATE.JSON) replaces the sensor status line for NOTICE_SECONDS.

A scene's ``create_scene`` may return a third element, ``set_sensors(values)``.
It gets the whole sensor values dict at startup, on every sensor swap and
whenever ``sensors.changed``, so new sensor-driven effects need no wiring here.
"""

from home.readout import sensor_lines, status_message
from persist.document import settings_from
from ui.buttons import NoButtons
from ui.menu import Menu
from ui.text_panel import TextPanel, panel_height

SENSOR_LINES = 3
NOTICE_SECONDS = 8


class App:
    def __init__(
        self,
        width,
        height,
        scene_module,
        sensors,
        now,
        buttons=None,
        set_rotation=None,
        store=None,
    ):
        self.width = width
        self.height = height
        self.buttons = buttons or NoButtons()
        self._set_rotation = set_rotation
        self.store = store
        saved = settings_from(store.load() if store else None)
        # Shown from the first tick on, so a slow WiFi connect doesn't eat it
        self._notice = store.notice if store else None
        self._notice_until = None
        scene = scene_module.create_scene(width, height)
        self.group, self._update_scene = scene[0], scene[1]
        # Optional third element: set_sensors(values), called with the whole
        # values dict whenever it changes. The scene decides what each value
        # means (e.g. CO2 -> creature brightness).
        self._scene_sensors = scene[2] if len(scene) > 2 else None
        # Sensor readout anchored to the bottom edge
        self.sensor_panel = TextPanel(
            self.group, width, height - panel_height(SENSOR_LINES), SENSOR_LINES
        )
        self.set_sensors(sensors, now)

        self.rotation = 0
        self._apply_rotation(saved["rotation"])
        self.sensors_on = saved["sensors_on"]
        self.sensor_panel.hidden = not self.sensors_on
        if store:
            store.provide("settings", self.settings)

        items = [
            (lambda: "ROTATE 90", self._rotate),
            (self._sensors_label, self._toggle_sensors),
        ]
        if store:
            items.append((lambda: "DUMP STATE", store.dump))
        items.append((lambda: "HIDE MENU", self._hide_menu))
        self.menu = Menu(items)
        # Menu on top of everything, anchored to the top edge; hidden until
        # the first button press
        self.menu_panel = TextPanel(self.group, width, 0, len(self.menu.items))
        self.menu_panel.hidden = True

    # ------------------------------------------------------------ settings
    def settings(self):
        """The ``settings`` section of the saved document."""
        return {"rotation": self.rotation, "sensors_on": self.sensors_on}

    def _changed(self):
        if self.store:
            self.store.mark_dirty()

    def _apply_rotation(self, degrees):
        self.rotation = degrees
        if self._set_rotation:
            self._set_rotation(degrees)

    # ------------------------------------------------------------ menu items
    def _rotate(self):
        self._apply_rotation((self.rotation + 90) % 360)
        self._changed()

    def _sensors_label(self):
        return "SENSORS ON" if self.sensors_on else "SENSORS OFF"

    def _toggle_sensors(self):
        self.sensors_on = not self.sensors_on
        self.sensor_panel.hidden = not self.sensors_on
        self._changed()

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
        if self._scene_sensors:
            self._scene_sensors(sensors.values)

    def tick(self, dt, now):
        self._update_menu(now)
        sensors = self.sensors
        sensors.poll(now)
        message = status_message(sensors, now, self._started)
        if self._notice:
            if self._notice_until is None:
                self._notice_until = now + NOTICE_SECONDS
            if now < self._notice_until:
                message = self._notice
            else:
                self._notice = None
        # Only build strings when something changed; set_lines also skips
        # redrawing when the text comes out the same.
        if sensors.changed or message != self._message:
            if sensors.changed and self._scene_sensors:
                self._scene_sensors(sensors.values)
            sensors.changed = False
            self._message = message
            self.sensor_panel.set_lines(sensor_lines(sensors.values, message))
        self._update_scene(dt)
        if self.store:
            self.store.tick(now)
