"""Desktop runner for the LED matrix scenes (run from src/).

    python3 run.py --scene pond
    python3 run.py --scene example_fish_scene --scale 10
    python3 run.py --settings ../my-settings.toml

HA config comes from hardware/settings.toml -- the same file deploy.sh copies
to the board as CIRCUITPY/settings.toml; --settings points at a different file.

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
import time

import simulator.virtual_matrix as vm
from app import App
from config import load_settings, poll_seconds
from home.fake_sensors import FakeSensors

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
    sensors = FakeSensors(poll_seconds(settings))
    app = App(args.width, args.height, scene, sensors, time.monotonic())

    display = vm.VirtualDisplay(
        args.width,
        args.height,
        scale=args.scale,
        title="%s -- virtual %dx%d" % (args.scene, args.width, args.height),
    )
    display.show(app.group)
    display.run(app.tick, fps=30)


if __name__ == "__main__":
    main()
