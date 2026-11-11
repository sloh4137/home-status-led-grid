"""Desktop runner for the LED matrix scenes (run from src/).

    python3 run.py --scene pond
    python3 run.py --scene example_fish_scene --scale 10
    python3 run.py --settings ../my-settings.toml

HA config comes from hardware/settings.toml -- the same file deploy.sh copies
to the board as CIRCUITPY/settings.toml; --settings points at a different file.
With HA_URL set it reads live values through home.ha_client.HAClient, otherwise
it shows FakeSensors values.

Keys stand in for the board's side buttons: Up / Down tap, Enter / Space hold
(select). The first press opens the menu.

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
from config import load_settings, poll_seconds
from home.fake_sensors import FakeSensors
from home.ha_client import from_settings
from ui.buttons import SimButtons

# The same file deploy.sh copies to the board as CIRCUITPY/settings.toml
DEFAULT_SETTINGS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "hardware", "settings.toml"
)

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
    args = parser.parse_args(argv)
    settings = load_settings(args.settings)

    scene = importlib.import_module("scenes." + args.scene)
    now = time.monotonic()
    # The CPython socket module has the same API as CircuitPython's
    # SocketPool, so the hardware client runs unchanged here.
    sensors = from_settings(socket, settings, poll_seconds(settings), now)
    if sensors is None:
        print("No HA_URL in %s; showing fake sensor values" % args.settings)
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

    app = App(args.width, args.height, scene, sensors, now, buttons, set_rotation)
    display.show(app.group)
    display.on_key(buttons.key)
    display.run(app.tick, fps=30)


if __name__ == "__main__":
    main()
