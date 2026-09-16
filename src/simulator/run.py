"""Unified desktop runner for the LED matrix scenes.

    python3 sim/run.py --scene fish --backend sim --width 64 --height 64 --scale 8
    python3 sim/run.py --scene ha --backend sim
    python3 sim/run.py --scene rain --width 96 --height 48
    python3 sim/run.py --scene fish --backend hw      # real Adafruit stack

--scene:   fish | rain | washer | ha   (ha = mock-Home-Assistant mode cycle)
--backend: sim = tkinter window (virtual_matrix.VirtualDisplay)
           hw  = real displayio + rgbmatrix + framebufferio.
                 Only runs where those modules exist (the MatrixPortal).
                 On a desktop it exits with a hint -- see below.

Tip: `pip install adafruit-blinka-displayio` gives you genuine displayio
classes on the desktop. scenes/ then builds against the *real* API and
--backend sim renders it, which catches places where the simulator is more
forgiving than hardware (e.g. out-of-range bitmap writes).
"""

import argparse
import importlib
import math
import os
import sys
import time

SIM_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SIM_DIR)
sys.path.insert(0, ROOT)     # To get scenes/
sys.path.insert(0, SIM_DIR)  # To get virtual_matrix

import virtual_matrix as vm

SCENES = ("example_fish_scene")


def _wrap_rain(update):
    """Standalone rain demo: sweep humidity so the drop density visibly changes."""
    t = [0.0]

    def wrapped(dt):
        t[0] += dt
        update(dt, 65 + 30 * math.sin(t[0] * 0.3))

    return wrapped


def _run_sim(group, update, width, height, scale, scene):
    display = vm.VirtualDisplay(
        width, height, scale=scale,
        title="%s -- virtual %dx%d" % (scene, width, height),
    )
    shown = {"group": None}

    def show(g):
        if g is not None and g is not shown["group"]:
            display.show(g)
            shown["group"] = g

    show(group)

    def tick(dt):
        # update() may return the group to show (the ha director swaps scenes)
        show(update(dt))

    display.run(tick, fps=30)


def _run_hw(group, update, width, height):
    try:
        import board
        import displayio
        import rgbmatrix
        import framebufferio
    except ImportError:
        sys.exit(
            "error: --backend hw needs the real CircuitPython modules "
            "(board/rgbmatrix/framebufferio), so it only runs on the "
            "MatrixPortal itself.\n"
            "Tip: 'pip install adafruit-blinka-displayio' gives you genuine "
            "displayio classes on this machine -- then --backend sim will "
            "exercise your scenes against the real API."
        )
    displayio.release_displays()
    matrix = rgbmatrix.RGBMatrix(
        width=width,
        height=height,
        bit_depth=4,
        rgb_pins=[
            board.MTX_R1, board.MTX_G1, board.MTX_B1,
            board.MTX_R2, board.MTX_G2, board.MTX_B2,
        ],
        addr_pins=[
            board.MTX_ADDRA, board.MTX_ADDRB, board.MTX_ADDRC,
            board.MTX_ADDRD, board.MTX_ADDRE,
        ],
        clock_pin=board.MTX_CLK,
        latch_pin=board.MTX_LAT,
        output_enable_pin=board.MTX_OE,
        tile=1,
        serpentine=True,
        doublebuffer=True,
    )
    display = framebufferio.FramebufferDisplay(matrix, auto_refresh=True)
    shown = {"group": None}

    def show(g):
        if g is not None and g is not shown["group"]:
            display.show(g)
            shown["group"] = g

    show(group)
    last = time.monotonic()
    while True:
        now = time.monotonic()
        dt = now - last
        last = now
        show(update(dt))
        time.sleep(max(0.0, 1 / 30 - (time.monotonic() - now)))


def main(argv=None):
    parser = argparse.ArgumentParser(description="LED matrix scene runner")
    parser.add_argument("--scene", choices=SCENES, default="example_fish_scene",
                        help="which scene to run (default: example_fish_scene)")
    parser.add_argument("--backend", choices=["sim", "hw"], default="sim",
                        help="sim = tkinter window, hw = real MatrixPortal stack")
    parser.add_argument("--width", type=int, default=64, help="matrix width in pixels")
    parser.add_argument("--height", type=int, default=64, help="matrix height in pixels")
    parser.add_argument("--scale", type=int, default=8,
                        help="screen px per LED (sim backend only)")
    args = parser.parse_args(argv)

    mod = importlib.import_module("scenes." + args.scene)
    group, update = mod.create_scene(args.width, args.height)
    if args.scene == "rain":
        update = _wrap_rain(update)

    if args.backend == "sim":
        _run_sim(group, update, args.width, args.height, args.scale, args.scene)
    else:
        _run_hw(group, update, args.width, args.height)


if __name__ == "__main__":
    main()
