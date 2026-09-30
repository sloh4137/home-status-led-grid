# code.py -- Pond scene for MatrixPortal S3 + 64x64 matrix
#
# Copy this file to the CIRCUITPY drive as code.py, and copy the shared scene
# code from the repo's src/ into a src/ folder next to it:
#
#   CIRCUITPY/
#     code.py
#     src/
#       _dio.py
#       behaviors/
#       creatures/
#       graphics/
#       scenes/
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

WIDTH, HEIGHT = 64, 64
FPS = 30

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
display = framebufferio.FramebufferDisplay(matrix, auto_refresh=True)

# ---------------------------------------------------------------- pond scene
group, update = create_scene(WIDTH, HEIGHT)
display.root_group = group

# ---------------------------------------------------------------- main loop
frame_time = 1 / FPS
last = time.monotonic()
while True:
    now = time.monotonic()
    dt = now - last
    last = now
    update(dt)
    time.sleep(max(0.0, frame_time - (time.monotonic() - now)))
