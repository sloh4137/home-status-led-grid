"""Desktop runner for the LED matrix scenes (run from src/).

    python3 run.py --scene pond
    python3 run.py --scene example_fish_scene --scale 10
    python3 run.py --settings ../my-settings.toml
    python3 run.py --state ../other-state.json

HA config comes from hardware/settings.toml -- the same file deploy.sh copies
to the board as CIRCUITPY/settings.toml; --settings points at a different file.
With HA_URL set it reads live values through home.ha_client.HAClient, otherwise
it shows FakeSensors values; --fake-sensors shows them even with HA_URL set.

With fake sensors, + / - set CO2 by hand in 100 ppm steps (the creatures dim
above 800 ppm) and 0 goes back to the slow 400-2200 ppm sweep.

Keys stand in for the board's side buttons: Up / Down tap, Enter / Space hold
(select). The first press opens the menu.

Menu settings and the pond's fish are saved to --state (default: state.json
at the repo root, git-ignored) at most once per PERSIST_SECONDS, and once
more when the window closes. It's the same JSON format as the board's state. Edit it while the
simulator is stopped; a running simulator overwrites it on its next save.

Renders into a tkinter window (simulator/virtual_matrix.VirtualDisplay) and
drives the same ``App`` as the MatrixPortal's code.py, so scenes, overlays and
the menu behave the same in both places.

Tip: `pip install adafruit-blinka-displayio` gives you genuine displayio
classes on the desktop. scenes/ then builds against the *real* API and the
simulator renders it, which catches places where the simulator is more
forgiving than hardware (e.g. out-of-range bitmap writes).
"""

import argparse
import importlib
import os
import socket
import time

import simulator.virtual_matrix as vm
from app import App
from config import load_settings, persist_seconds, poll_seconds
from home.fake_sensors import FakeSensors
from home.ha_client import from_settings
from persist.store import FileBackend, Store
from ui.buttons import SimButtons

# The same file deploy.sh copies to the board as CIRCUITPY/settings.toml
SRC = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SETTINGS = os.path.join(SRC, "hardware", "settings.toml")
# The desktop save, git-ignored
DEFAULT_STATE = os.path.join(os.path.dirname(SRC), "state.json")

SCENES = ("example_fish_scene", "pond")


def main(argv=None):
    parser = argparse.ArgumentParser(description="LED matrix scene runner")
    parser.add_argument(
        "--scene",
        choices=SCENES,
        default="pond",
        help="which scene to run (default: pond)",
    )
    parser.add_argument("--width", type=int, default=64, help="matrix width in pixels")
    parser.add_argument(
        "--height", type=int, default=64, help="matrix height in pixels"
    )
    parser.add_argument("--scale", type=int, default=8, help="screen px per LED")
    parser.add_argument(
        "--settings",
        default=DEFAULT_SETTINGS,
        help="settings.toml to read HA config from (default: hardware/settings.toml)",
    )
    parser.add_argument(
        "--state",
        default=DEFAULT_STATE,
        help="JSON file to load and save the state in (default: state.json at the repo root)",
    )
    parser.add_argument(
        "--fake-sensors",
        action="store_true",
        help="show FakeSensors values even when HA_URL is set (+ / - / 0 drive CO2)",
    )
    args = parser.parse_args(argv)
    settings = load_settings(args.settings)

    scene = importlib.import_module("scenes." + args.scene)
    now = time.monotonic()
    # The CPython socket module has the same API as CircuitPython's
    # SocketPool, so the hardware client runs unchanged here.
    sensors = None
    if not args.fake_sensors:
        sensors = from_settings(socket, settings, poll_seconds(settings), now)
    if sensors is None and not args.fake_sensors:
        print("No HA_URL in %s; showing fake sensor values" % args.settings)
    if sensors is None:
        sensors = FakeSensors(poll_seconds(settings))
    buttons = SimButtons()
    display = vm.VirtualDisplay(
        args.width,
        args.height,
        scale=args.scale,
        title="%s -- virtual %dx%d" % (args.scene, args.width, args.height),
    )

    def set_rotation(degrees):
        display.rotation = degrees

    store = Store(FileBackend(args.state), persist_seconds(settings), now)
    app = App(
        args.width,
        args.height,
        scene,
        sensors,
        now,
        buttons,
        set_rotation,
        store,
        settings,
    )
    display.show(app.group)
    sensor_key = getattr(sensors, "key", None)

    def on_key(keysym):
        buttons.key(keysym)
        if sensor_key:
            sensor_key(keysym)

    display.on_key(on_key)
    display.run(app.tick, fps=30)
    # The window was closed; a desktop "power loss" shouldn't lose changes
    store.flush(time.monotonic())


if __name__ == "__main__":
    main()
