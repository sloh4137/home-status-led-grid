# code.py -- Pond scene for MatrixPortal S3 + 64x64 matrix
#
# Copy this file to the CIRCUITPY drive as code.py, and copy the shared scene
# code from the repo's src/ into a src/ folder next to it:
#
#   CIRCUITPY/
#     code.py
#     lib/
#       adafruit_imageload/   (from the CircuitPython library bundle)
#     src/
#       _dio.py
#       _imageload.py
#       behaviors/
#       creatures/
#       graphics/
#       scenes/
#       sprites/
#
# The scene modules import each other by top-level name (e.g.
# `from _dio import dio`), so code.py adds /src to sys.path before importing.
#
# simulator/ and run.py are desktop-only and don't need to be copied.
#
# The scene modules are shared with the desktop runner (src/run.py), so
# animations are developed and previewed in the simulator, then run here
# unchanged.
#
# Hardware note: the 64x64 panel needs the Address-E solder jumper on the
# MatrixPortal closed (middle pad shorted to "8" for Adafruit panels).

import sys
import time

import board
import displayio
import framebufferio
import rgbmatrix

sys.path.insert(0, "/src")

from scenes.pond import create_scene  # noqa: E402 -- needs /src on sys.path
from behaviors.flocking import FlockingBehavior  # noqa: E402
import scenes.pond  # noqa: E402

WIDTH, HEIGHT = 64, 64
FPS = 30
DEBUG = True  # time physics, render and refresh and print them to the serial console
STATS_EVERY = 30  # frames between timing printouts on the serial console

# ---------------------------------------------------------------- matrix setup
displayio.release_displays()
matrix = rgbmatrix.RGBMatrix(
    width=WIDTH,
    height=HEIGHT,
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
display = framebufferio.FramebufferDisplay(matrix, auto_refresh=False)

# ---------------------------------------------------------------- pond scene
group, update = create_scene(WIDTH, HEIGHT)
display.root_group = group

# ---------------------------------------------------------------- timing
# With DEBUG on, physics, render() and display.refresh() are timed separately
# and printed to the serial console every STATS_EVERY frames.
# render() is called from inside the behavior's update(), so wrap it to
# accumulate its time separately; physics = update time - render time.
render_ns = 0
frames = 0
update_total = render_total = refresh_total = 0
stats_start = time.monotonic_ns()

if DEBUG:
    _render = FlockingBehavior.render

    def _timed_render(self):
        global render_ns
        t = time.monotonic_ns()
        _render(self)
        render_ns += time.monotonic_ns() - t

    FlockingBehavior.render = _timed_render

    # The pond background is drawn into the same canvas, so count it as render
    _draw_frame = scenes.pond.draw_frame

    def _timed_draw_frame(*args):
        global render_ns
        t = time.monotonic_ns()
        _draw_frame(*args)
        render_ns += time.monotonic_ns() - t

    scenes.pond.draw_frame = _timed_draw_frame


def timed_frame(dt):
    global render_ns, frames, update_total, render_total, refresh_total
    global stats_start

    render_ns = 0
    t0 = time.monotonic_ns()
    update(dt)
    t1 = time.monotonic_ns()
    display.refresh()
    t2 = time.monotonic_ns()

    update_total += t1 - t0
    render_total += render_ns
    refresh_total += t2 - t1
    frames += 1
    if frames == STATS_EVERY:
        elapsed = time.monotonic_ns() - stats_start
        print(
            "fps %.1f | physics %.1f ms | render %.1f ms | refresh %.1f ms"
            % (
                frames * 1e9 / elapsed,
                (update_total - render_total) / frames / 1e6,
                render_total / frames / 1e6,
                refresh_total / frames / 1e6,
            )
        )
        frames = 0
        update_total = render_total = refresh_total = 0
        stats_start = time.monotonic_ns()


# ---------------------------------------------------------------- main loop
frame_time = 1 / FPS
last = time.monotonic()
while True:
    now = time.monotonic()
    dt = now - last
    last = now

    if DEBUG:
        timed_frame(dt)
    else:
        update(dt)
        display.refresh()

    time.sleep(max(0.0, frame_time - (time.monotonic() - now)))
