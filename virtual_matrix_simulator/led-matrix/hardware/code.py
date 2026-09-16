# code.py -- Fish tank + Home Assistant status display for MatrixPortal + 64x64 matrix
#
# Drop this file onto the CIRCUITPY drive as code.py, add a settings.toml
# (see ../settings.toml.example), and copy the required libraries into lib/.
#
# Required .mpy libraries in lib/:
#   adafruit_matrixportal / adafruit_portalbase (optional helpers)
#   adafruit_requests.mpy
#   S3 only: nothing extra (wifi/socketpool/ssl are built in)
#   M4 only: adafruit_esp32spi/, adafruit_bus_device/
#
# Hardware note: the 64x64 panel needs the Address-E solder jumper on the
# MatrixPortal closed (middle pad shorted to "8" for Adafruit panels).

import os
import time
import math
import random

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

# ---------------------------------------------------------------- tiny 3x5 font
_FONT_3X5 = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "001", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    "%": ("101", "001", "010", "100", "101"),
    "H": ("101", "101", "111", "101", "101"),
    " ": ("000", "000", "000", "000", "000"),
}


def draw_text(bitmap, text, x, y, color_index, scale=1):
    cx = x
    for ch in text.upper():
        glyph = _FONT_3X5.get(ch, _FONT_3X5[" "])
        for gy, row in enumerate(glyph):
            for gx, pixel in enumerate(row):
                if pixel == "1":
                    for sy in range(scale):
                        for sx in range(scale):
                            bitmap[cx + gx * scale + sx, y + gy * scale + sy] = color_index
        cx += 4 * scale


def bitmap_from_art(art, char_to_index):
    h = len(art)
    w = max(len(row) for row in art)
    bmp = displayio.Bitmap(w, h, 256)
    for y, row in enumerate(art):
        for x, ch in enumerate(row):
            bmp[x, y] = char_to_index.get(ch, 0)
    return bmp


# ---------------------------------------------------------------- fish tank scene
FISH_A = [
    "....................",
    ".......bbb..........",
    ".....bbbbbbb........",
    "....bbbbbbbbb.......",
    "..bbbbbbbbbbbb.tt...",
    ".bbebbbbbbbbb...ttt.",
    "..bbbbbbbbbbbb..ttt.",
    "....bbbbbbbbb...ttt.",
    ".....bbbbbbb...tt...",
    ".......bbb..........",
    "....................",
]
FISH_B = [
    "....................",
    ".......bbb.....tt...",
    ".....bbbbbbb...ttt..",
    "....bbbbbbbbb..ttt..",
    "..bbbbbbbbbbbb..ttt.",
    ".bbebbbbbbbbb...ttt.",
    "..bbbbbbbbbbbb.tt...",
    "....bbbbbbbbb.......",
    ".....bbbbbbb........",
    ".......bbb..........",
    "....................",
]
FISH_COLORS = [
    (0xFF7B1C, 0xFFFFFF, 0xFFD23F),
    (0x2E9BFF, 0xFFFFFF, 0x7FD4FF),
    (0xB45CFF, 0xFFFFFF, 0xE0A6FF),
]


class FishTank:
    def __init__(self):
        self.group = displayio.Group()
        # water gradient background
        pal = displayio.Palette(16)
        for i in range(16):
            f = i / 15
            pal[i] = (int(4 + 10 * f) << 16) | (int(10 + 30 * f) << 8) | int(40 + 60 * f)
        bg = displayio.Bitmap(WIDTH, HEIGHT, 16)
        for y in range(HEIGHT):
            idx = int((y / HEIGHT) * 15)
            for x in range(WIDTH):
                bg[x, y] = idx
        self.group.append(displayio.TileGrid(bg, pixel_shader=pal))

        # seaweed (precomputed sway frames)
        wpal = displayio.Palette(2)
        wpal.make_transparent(0)
        wpal[1] = 0x1FA84F
        self.weed_frames = []
        for phase in range(4):
            bmp = displayio.Bitmap(5, 18, 2)
            for y in range(18):
                x = 2 + int(math.sin(y * 0.45 + phase * 1.57) * 1.6)
                bmp[x, y] = 1
                if y > 12:
                    bmp[max(0, x - 1), y] = 1
            self.weed_frames.append(bmp)
        self.weeds = []
        for wx in (6, 30, 52):
            grid = displayio.TileGrid(self.weed_frames[0], pixel_shader=wpal,
                                      x=wx, y=HEIGHT - 18)
            self.group.append(grid)
            self.weeds.append((grid, random.uniform(0, 4)))

        # bubbles
        bpal = displayio.Palette(2)
        bpal.make_transparent(0)
        bpal[1] = 0x9BDCFF
        self.bubbles = []
        for _ in range(14):
            bmp = displayio.Bitmap(3, 3, 2)
            for (x, y) in ((1, 0), (0, 1), (2, 1), (1, 2)):
                bmp[x, y] = 1
            grid = displayio.TileGrid(bmp, pixel_shader=bpal,
                                      x=random.randint(0, WIDTH - 3),
                                      y=random.randint(0, HEIGHT))
            self.group.append(grid)
            self.bubbles.append({"grid": grid, "fy": float(grid.y),
                                 "speed": random.uniform(8, 20),
                                 "wobble": random.uniform(0, 6.28)})

        # fish
        self.fishes = []
        specs = [(FISH_COLORS[0], 12, 14, -1),
                 (FISH_COLORS[1], 30, 10, 1),
                 (FISH_COLORS[2], 44, 18, -1)]
        for colors, y, speed, direction in specs:
            cmap = {".": 0, "b": 1, "e": 2, "t": 3}
            bmp_a = bitmap_from_art(FISH_A, cmap)
            bmp_b = bitmap_from_art(FISH_B, cmap)
            if direction > 0:
                for src, dst in ((bmp_a, displayio.Bitmap(20, 11, 256)),
                                 (bmp_b, displayio.Bitmap(20, 11, 256))):
                    for yy in range(11):
                        for xx in range(20):
                            dst[19 - xx, yy] = src[xx, yy]
                    if src is bmp_a:
                        bmp_a = dst
                    else:
                        bmp_b = dst
            pal = displayio.Palette(4)
            pal.make_transparent(0)
            pal[1], pal[2], pal[3] = colors
            grid = displayio.TileGrid(bmp_a, pixel_shader=pal, x=0, y=y)
            self.group.append(grid)
            self.fishes.append({"grid": grid, "frames": (bmp_a, bmp_b),
                                "y_base": y, "speed": speed,
                                "direction": direction,
                                "x": random.uniform(-25, WIDTH + 5),
                                "phase": random.uniform(0, 6.28), "t": 0.0})
        self.t = 0.0

    def update(self, dt):
        self.t += dt
        for f in self.fishes:
            f["t"] += dt
            f["x"] += f["direction"] * f["speed"] * dt
            w = 20
            if f["direction"] < 0 and f["x"] < -w:
                f["x"] = WIDTH + random.uniform(0, 20)
                f["y_base"] = random.randint(6, HEIGHT - 18)
            elif f["direction"] > 0 and f["x"] > WIDTH:
                f["x"] = -w - random.uniform(0, 20)
                f["y_base"] = random.randint(6, HEIGHT - 18)
            f["grid"].x = int(f["x"])
            f["grid"].y = int(f["y_base"] + math.sin(f["t"] * 2.2 + f["phase"]) * 3)
            f["grid"].bitmap = f["frames"][int(f["t"] * 6) % 2]
        for b in self.bubbles:
            b["fy"] -= b["speed"] * dt
            b["grid"].y = int(b["fy"])
            b["grid"].x += int(math.sin(self.t * 3 + b["wobble"]) * 0.6)
            if b["fy"] < -4:
                b["grid"].x = random.randint(0, WIDTH - 3)
                b["fy"] = float(HEIGHT + random.randint(0, 10))
        for grid, phase in self.weeds:
            grid.bitmap = self.weed_frames[int(self.t * 2 + phase) % 4]


# ---------------------------------------------------------------- rain scene
class Rain:
    """Humidity readout + rain density follows the humidity sensor."""

    def __init__(self):
        self.group = displayio.Group()
        pal = displayio.Palette(2)
        pal[1] = 0x0A0F1E
        bg = displayio.Bitmap(WIDTH, HEIGHT, 2)
        bg.fill(1)
        self.group.append(displayio.TileGrid(bg, pixel_shader=pal))

        dpal = displayio.Palette(2)
        dpal.make_transparent(0)
        dpal[1] = 0x4FC3FF
        self.drops = []
        for _ in range(60):
            bmp = displayio.Bitmap(1, 4, 2)
            bmp[0, 0] = bmp[0, 1] = bmp[0, 2] = 1
            grid = displayio.TileGrid(bmp, pixel_shader=dpal,
                                      x=random.randint(0, WIDTH - 1),
                                      y=random.randint(-HEIGHT, HEIGHT))
            self.group.append(grid)
            self.drops.append({"grid": grid, "speed": random.uniform(40, 90)})

        tpal = displayio.Palette(2)
        tpal.make_transparent(0)
        tpal[1] = 0xFFFFFF
        self.text_bmp = displayio.Bitmap(WIDTH, 12, 2)
        self.group.append(displayio.TileGrid(self.text_bmp, pixel_shader=tpal, x=0, y=2))
        self.humidity = -1

    def update(self, dt, humidity):
        if humidity != self.humidity:
            self.humidity = humidity
            self.text_bmp.fill(0)
            label = "%d%%" % int(humidity)
            tw = (len(label) * 4 - 1) * 2
            draw_text(self.text_bmp, label, (WIDTH - tw) // 2, 0, 1, scale=2)
        visible = int(8 + max(0, humidity - 30) / 70 * 52)
        for i, d in enumerate(self.drops):
            g = d["grid"]
            if i >= visible:
                g.y = -100
                continue
            if g.y <= -100:
                g.y = random.randint(-20, 0)
            g.y = int(g.y + d["speed"] * dt)
            if g.y > HEIGHT:
                g.y = random.randint(-24, -4)
                g.x = random.randint(0, WIDTH - 1)


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
tank = FishTank()
rain = Rain()
display.show(tank.group)
mode = "tank"

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
        new_mode = "tank"  # TODO: washer scene (see sim/ha_status.py)
    elif humidity >= 70:
        new_mode = "rain"
    else:
        new_mode = "tank"
    if new_mode != mode:
        mode = new_mode
        display.show(rain.group if mode == "rain" else tank.group)

    dt = 1 / 30
    if mode == "rain":
        rain.update(dt, humidity)
    else:
        tank.update(dt)
    time.sleep(dt)
