# code.py -- Fish tank + Home Assistant status display for MatrixPortal + 64x64 matrix
#
# Copy this file to the CIRCUITPY drive as code.py, copy the whole scenes/
# folder to the CIRCUITPY drive as well (code.py does `from scenes.fish import
# ...`), add a settings.toml (see ../settings.toml.example), and copy the
# required libraries into lib/.
#
# Required .mpy libraries in lib/:
#   adafruit_requests.mpy
#   S3 only: nothing extra (wifi/socketpool/ssl are built in)
#   M4 only: adafruit_esp32spi/, adafruit_bus_device/
#
# The scenes/ modules are shared with the desktop simulator (sim/run.py), so
# animations are developed and previewed on your Mac, then run here unchanged.
#
# Hardware note: the 64x64 panel needs the Address-E solder jumper on the
# MatrixPortal closed (middle pad shorted to "8" for Adafruit panels).

import os
import time

import board
import displayio
import framebufferio
import rgbmatrix

WIDTH, HEIGHT = 64, 64

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

# ---------------------------------------------------------------- shared scenes
# Same code the desktop simulator runs (sim/run.py). Each create_scene returns
# (group, update); rain's update takes (dt, humidity).
from scenes.fish import create_scene as create_fish
from scenes.rain import create_scene as create_rain
from scenes.washer import create_scene as create_washer

tank_group, tank_update = create_fish(WIDTH, HEIGHT)
rain_group, rain_update = create_rain(WIDTH, HEIGHT)
washer_group, washer_update = create_washer(WIDTH, HEIGHT)
GROUPS = {"tank": tank_group, "rain": rain_group, "washer": washer_group}

display.show(tank_group)
mode = "tank"


# ---------------------------------------------------------------- network + HA
def get_requests_session():
    """adafruit_requests Session over WiFi. S3 = native wifi, M4 = ESP32 SPI."""
    ssid = os.getenv("CIRCUITPY_WIFI_SSID")
    password = os.getenv("CIRCUITPY_WIFI_PASSWORD")
    if not ssid:
        return None
    try:  # MatrixPortal S3: native WiFi
        import wifi
        import socketpool
        import ssl
        import adafruit_requests

        if not wifi.radio.connected:
            wifi.radio.connect(ssid, password)
        pool = socketpool.SocketPool(wifi.radio)
        return adafruit_requests.Session(pool, ssl.create_default_context())
    except ImportError:
        pass
    try:  # MatrixPortal M4: ESP32 coprocessor
        import busio
        from digitalio import DigitalInOut
        from adafruit_esp32spi import adafruit_esp32spi
        import adafruit_esp32spi.adafruit_esp32spi_socket as esp_socket
        import adafruit_requests

        esp32_cs = DigitalInOut(board.ESP_CS)
        esp32_ready = DigitalInOut(board.ESP_BUSY)
        esp32_reset = DigitalInOut(board.ESP_RESET)
        spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
        esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)
        esp.connect_AP(ssid, password)
        adafruit_requests.set_socket(esp_socket, esp)
        return adafruit_requests.Session()
    except Exception as e:  # pylint: disable=broad-except
        print("network unavailable:", e)
        return None


HA_URL = os.getenv("HA_URL", "")
HA_TOKEN = os.getenv("HA_TOKEN", "")
HUMIDITY_ENTITY = os.getenv("HUMIDITY_ENTITY", "sensor.bathroom_humidity")
WASHER_ENTITY = os.getenv("WASHER_ENTITY", "sensor.washer_status")


def ha_state(session, entity):
    try:
        r = session.get(
            HA_URL + "/api/states/" + entity,
            headers={"Authorization": "Bearer " + HA_TOKEN},
        )
        return r.json().get("state")
    except Exception as e:  # pylint: disable=broad-except
        print("HA poll failed:", e)
        return None


# ---------------------------------------------------------------- main loop
session = get_requests_session()
last_poll = 0.0
humidity = 45.0
washer = "off"

while True:
    now = time.monotonic()
    if session and HA_URL and now - last_poll > 30:
        last_poll = now
        h = ha_state(session, HUMIDITY_ENTITY)
        w = ha_state(session, WASHER_ENTITY)
        try:
            humidity = float(h)
        except (TypeError, ValueError):
            pass
        if w in ("on", "off"):
            washer = w

    if washer == "on":
        new_mode = "washer"
    elif humidity >= 70:
        new_mode = "rain"
    else:
        new_mode = "tank"
    if new_mode != mode:
        mode = new_mode
        display.show(GROUPS[mode])

    dt = 1 / 30
    if mode == "rain":
        rain_update(dt, humidity)
    elif mode == "washer":
        washer_update(dt)
    else:
        tank_update(dt)
    time.sleep(dt)
