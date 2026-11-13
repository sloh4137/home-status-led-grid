# code.py -- Pond scene for MatrixPortal S3 + 64x64 matrix
#
# Copy this file to the CIRCUITPY drive as code.py, and copy the shared scene
# code from the repo's src/ into a src/ folder next to it:
#
#   CIRCUITPY/
#     code.py
#     settings.toml           (from src/hardware/settings.toml.example)
#     lib/
#       adafruit_imageload/   (from the CircuitPython library bundle)
#     src/
#       _dio.py
#       _imageload.py
#       config.py
#       behaviors/
#       creatures/
#       graphics/
#       home/
#       persist/
#       scenes/
#       sprites/
#       ui/
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
# ./deploy.sh from the repo root does all of the copying (see README.md).
#
# Home Assistant setup, in settings.toml:
#   CIRCUITPY_WIFI_SSID / CIRCUITPY_WIFI_PASSWORD   WiFi
#   HA_URL            e.g. "http://192.168.1.10:8123" (use an IP, plain http)
#   HA_TOKEN          HA -> your profile -> Security -> Long-lived access tokens
#   HA_CO2_ENTITY, HA_TEMPERATURE_ENTITY, HA_HUMIDITY_ENTITY   entity IDs
#   HA_POLL_SECONDS   1-60, default 5
#   PERSIST_SECONDS   10-3600, default 60: minimum seconds between state saves
# The readout shows WIFI... while connecting, then the values, or NO WIFI /
# NO HA CFG if setup failed, or HA OFFLINE after 3 intervals without a read.
#
# Buttons: UP / DOWN open the menu, a tap moves the highlight and holding
# either for ~0.6 s selects. Items: ROTATE 90, SENSORS ON/OFF, HIDE MENU.
# The rotation and SENSORS ON/OFF are saved to microcontroller.nvm at most
# once per PERSIST_SECONDS, so a change made just before a power loss is lost.
# RESET is a hardware reset and only reboots; code can't read it.
#
# Hardware note: the 64x64 panel needs the Address-E solder jumper on the
# MatrixPortal closed (middle pad shorted to "8" for Adafruit panels).

import sys
import time

import board
import displayio
import framebufferio
import microcontroller
import rgbmatrix

sys.path.insert(0, "/src")

from app import App  # noqa: E402 -- needs /src on sys.path
from behaviors.flocking import FlockingBehavior  # noqa: E402
from config import load_settings, persist_seconds, poll_seconds  # noqa: E402
from home.ha_client import from_settings  # noqa: E402
from home.no_sensors import NoSensors  # noqa: E402
from persist.store import NvmBackend, Store  # noqa: E402
import scenes.pond  # noqa: E402
from ui.buttons import KeypadButtons  # noqa: E402

WIDTH, HEIGHT = 64, 64
FPS = 30
DEBUG = True  # time physics, render, net and refresh; print them to the serial console
STATS_EVERY = 30  # frames between timing printouts on the serial console

# ---------------------------------------------------------------- matrix setup
displayio.release_displays()
matrix = rgbmatrix.RGBMatrix(
    width=WIDTH,
    height=HEIGHT,
    bit_depth=4,
    rgb_pins=[
        board.MTX_R1,
        board.MTX_G1,
        board.MTX_B1,
        board.MTX_R2,
        board.MTX_G2,
        board.MTX_B2,
    ],
    addr_pins=[
        board.MTX_ADDRA,
        board.MTX_ADDRB,
        board.MTX_ADDRC,
        board.MTX_ADDRD,
        board.MTX_ADDRE,
    ],
    clock_pin=board.MTX_CLK,
    latch_pin=board.MTX_LAT,
    output_enable_pin=board.MTX_OE,
    tile=1,
    serpentine=True,
    doublebuffer=True,
)
display = framebufferio.FramebufferDisplay(matrix, auto_refresh=False)


def set_rotation(degrees):
    # The panel is square, so the group's width/height stay the same
    display.rotation = degrees


# ---------------------------------------------------------------- app
settings = load_settings()
print("nvm: %d bytes" % len(microcontroller.nvm))
store = Store(
    NvmBackend(microcontroller.nvm), persist_seconds(settings), time.monotonic()
)
app = App(
    WIDTH,
    HEIGHT,
    scenes.pond,
    NoSensors("WIFI..."),
    time.monotonic(),
    KeypadButtons(),
    set_rotation,
    store,
)
display.root_group = app.group
display.refresh()  # show WIFI... while connecting, which can take seconds


# ---------------------------------------------------------------- HA
# HA config comes from CIRCUITPY/settings.toml (read with os.getenv).
# CircuitPython usually joins CIRCUITPY_WIFI_SSID by itself at boot; connect
# here only if it hasn't. This blocks, but only once at startup.
def connect_sensors(settings):
    if not settings.get("HA_URL"):
        print("HA: no HA_URL in settings.toml")
        return NoSensors("NO HA CFG")

    import socketpool
    import wifi

    if not wifi.radio.connected:
        ssid = settings.get("CIRCUITPY_WIFI_SSID")
        if not ssid:
            print("WiFi: no CIRCUITPY_WIFI_SSID in settings.toml")
            return NoSensors("NO WIFI")
        try:
            wifi.radio.connect(ssid, settings.get("CIRCUITPY_WIFI_PASSWORD", ""))
        except (ConnectionError, OSError) as e:
            print("WiFi:", e)
            return NoSensors("NO WIFI")
    print("WiFi: %s" % wifi.radio.ipv4_address)

    pool = socketpool.SocketPool(wifi.radio)
    try:
        return from_settings(
            pool,
            settings,
            poll_seconds(settings),
            time.monotonic(),
        )
    except ValueError as e:
        print("HA:", e)
        return NoSensors("NO HA CFG")


sensors = connect_sensors(settings)
app.set_sensors(sensors, time.monotonic())

# ---------------------------------------------------------------- timing
# With DEBUG on, physics, render(), sensors.poll() (net) and display.refresh()
# are timed separately and printed to the serial console every STATS_EVERY
# frames. render() and poll() are called from inside app.tick(), so they are
# wrapped to accumulate their time separately;
# physics = tick time - render time - net time.
render_ns = 0
net_ns = 0
frames = 0
update_total = render_total = refresh_total = 0
net_total = net_max = 0
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

    _poll = sensors.poll

    def _timed_poll(now):
        global net_ns
        t = time.monotonic_ns()
        _poll(now)
        net_ns = time.monotonic_ns() - t

    sensors.poll = _timed_poll


def timed_frame(dt, now):
    global render_ns, net_ns, frames, update_total, render_total, refresh_total
    global net_total, net_max, stats_start

    render_ns = 0
    net_ns = 0
    t0 = time.monotonic_ns()
    app.tick(dt, now)
    t1 = time.monotonic_ns()
    display.refresh()
    t2 = time.monotonic_ns()

    update_total += t1 - t0
    render_total += render_ns
    net_total += net_ns
    net_max = max(net_max, net_ns)
    refresh_total += t2 - t1
    frames += 1
    if frames == STATS_EVERY:
        elapsed = time.monotonic_ns() - stats_start
        print(
            "fps %.1f | physics %.1f ms | render %.1f ms | net %.1f (max %.1f) ms"
            " | refresh %.1f ms | ha ok %s"
            % (
                frames * 1e9 / elapsed,
                (update_total - render_total - net_total) / frames / 1e6,
                render_total / frames / 1e6,
                net_total / frames / 1e6,
                net_max / 1e6,
                refresh_total / frames / 1e6,
                "never" if sensors.last_ok is None
                else "%.0fs ago" % (time.monotonic() - sensors.last_ok),
            )
        )
        frames = 0
        update_total = render_total = refresh_total = 0
        net_total = net_max = 0
        stats_start = time.monotonic_ns()


# ---------------------------------------------------------------- main loop
frame_time = 1 / FPS
last = time.monotonic()
while True:
    now = time.monotonic()
    dt = now - last
    last = now

    if DEBUG:
        timed_frame(dt, now)
    else:
        app.tick(dt, now)
        display.refresh()

    time.sleep(max(0.0, frame_time - (time.monotonic() - now)))
