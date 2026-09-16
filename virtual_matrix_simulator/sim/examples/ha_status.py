"""Home Assistant-driven display modes for the virtual 64x64 LED matrix.

Run on your Mac:  python3 sim/ha_status.py

This shows the *pattern* your MatrixPortal code will use:
  1. poll Home Assistant (here: a mock client cycling through scenarios)
  2. pick a scene based on sensor states
  3. render it with the same displayio-style primitives as fish_tank.py

On the real Portal, MockHA is replaced by adafruit_requests calls to
http://<ha-host>:8123/api/states/<entity_id> -- see hardware/code.py.
"""

import math
import random
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
import virtual_matrix as vm

# ----------------------------------------------------------------------------
# Mock Home Assistant: cycles through scenarios so you can preview each mode.
# Replace with real REST calls on hardware (see hardware/code.py).
# ----------------------------------------------------------------------------

SCENARIOS = [
    {"humidity": 48, "washer": "off", "label": "calm"},
    {"humidity": 83, "washer": "off", "label": "humid -> rain"},
    {"humidity": 55, "washer": "on", "label": "washer running"},
]


class MockHA:
    def __init__(self, dwell=9.0):
        self.dwell = dwell
        self.t = 0.0
        self.idx = 0

    def poll(self, dt):
        self.t += dt
        if self.t >= self.dwell:
            self.t = 0.0
            self.idx = (self.idx + 1) % len(SCENARIOS)
        return SCENARIOS[self.idx]


# ----------------------------------------------------------------------------
# Rain scene: droplet density follows humidity; numeric readout on top.
# ----------------------------------------------------------------------------

def make_rain_scene(width=64, height=64):
    group = vm.Group()

    bg_pal = vm.Palette(2)
    bg_pal[1] = 0x0A0F1E
    bg = vm.Bitmap(width, height, 2)
    bg.fill(1)
    group.append(vm.TileGrid(bg, bg_pal))

    drop_pal = vm.Palette(2)
    drop_pal.make_transparent(0)
    drop_pal[1] = 0x4FC3FF

    drops = []
    for _ in range(60):  # pool; visible count scales with humidity
        bmp = vm.Bitmap(1, 4, 2)
        bmp[0, 0] = 1
        bmp[0, 1] = 1
        bmp[0, 2] = 1
        grid = vm.TileGrid(bmp, drop_pal,
                           x=random.randint(0, width - 1), y=random.randint(-height, height))
        drops.append({"grid": grid, "speed": random.uniform(40, 90)})
        group.append(grid)

    # humidity readout, e.g. "83%", drawn once per humidity change
    text_pal = vm.Palette(2)
    text_pal.make_transparent(0)
    text_pal[1] = 0xFFFFFF
    text_bmp = vm.Bitmap(width, 12, 2)
    text_grid = vm.TileGrid(text_bmp, text_pal, x=0, y=2)
    group.append(text_grid)

    state = {"humidity": -1}

    def set_humidity(h):
        if h == state["humidity"]:
            return
        state["humidity"] = h
        text_bmp.fill(0)
        label = "%d%%" % h
        vm.draw_text(text_bmp, label,
                     (width - vm.text_width(label, scale=2)) // 2, 0,
                     color_index=1, scale=2)

    def update(dt, humidity):
        set_humidity(humidity)
        # visible drops ~ humidity mapped 30%..100% -> 8..60 drops
        visible = int(8 + max(0, humidity - 30) / 70 * 52)
        for i, d in enumerate(drops):
            g = d["grid"]
            if i >= visible:
                g.y = -100  # park unused drops off-screen
                continue
            if g.y < -100:  # re-enter when becoming visible
                g.y = random.randint(-20, 0)
            g.y += d["speed"] * dt
            if g.y > height:
                g.y = random.randint(-24, -4)
                g.x = random.randint(0, width - 1)

    return group, update


# ----------------------------------------------------------------------------
# Washer scene: washing-machine icon with a spinning drum.
# ----------------------------------------------------------------------------

WASHER_BODY = [
    "........................",
    ".1111111111111111111111.",
    ".1111111111111111111111.",
    ".1000000000000000000001.",
    ".1000000000000000000001.",
    ".1000022222222222000001.",
    ".1000222222222222200001.",
    ".1002222222222222220001.",
    ".1002222222222222220001.",
    ".1022222222222222222001.",
    ".1022222222222222222001.",
    ".1022222222222222222001.",
    ".1002222222222222220001.",
    ".1002222222222222220001.",
    ".1000222222222222200001.",
    ".1000022222222222000001.",
    ".1000000000000000000001.",
    ".1000000000000000000001.",
    ".1111111111111111111111.",
    "........................",
]


def make_washer_scene(width=64, height=64):
    group = vm.Group()

    bg_pal = vm.Palette(2)
    bg_pal[1] = 0x101418
    bg = vm.Bitmap(width, height, 2)
    bg.fill(1)
    group.append(vm.TileGrid(bg, bg_pal))

    pal = vm.Palette(4)
    pal.make_transparent(0)
    pal[1] = 0x3A4552   # body
    pal[2] = 0x7FD4FF   # door glass
    pal[3] = 0xFFFFFF   # drum highlight

    body = vm.bitmap_from_art(WASHER_BODY, {"1": 1, "0": 0, "2": 2})
    wx, wy = (width - 24) // 2, (height - 20) // 2
    group.append(vm.TileGrid(body, pal, x=wx, y=wy))

    # spinning drum dashes: 4 frames of a rotating arc inside the door
    drum_frames = []
    cx, cy, r = 11, 9, 6
    for phase in range(4):
        bmp = vm.Bitmap(24, 20, 4)
        for k in range(3):
            ang = phase * math.pi / 2 + k * 0.5
            dx, dy = int(cx + math.cos(ang) * r), int(cy + math.sin(ang) * r)
            if 0 <= dx < 24 and 0 <= dy < 20:
                bmp[dx, dy] = 3
                bmp[min(23, dx + 1), dy] = 3
        drum_frames.append(bmp)
    drum = vm.TileGrid(drum_frames[0], pal, x=wx, y=wy)
    group.append(drum)

    # pulsing "running" glow dots underneath
    dot_pal = vm.Palette(2)
    dot_pal.make_transparent(0)
    dot_pal[1] = 0x2EFF7B
    dots = vm.Bitmap(24, 3, 2)
    dot_grid = vm.TileGrid(dots, dot_pal, x=wx, y=wy + 24)
    group.append(dot_grid)

    t = [0.0]

    def update(dt):
        t[0] += dt
        drum.bitmap = drum_frames[int(t[0] * 6) % 4]
        dots.fill(0)
        n = 1 + int(t[0] * 2) % 3  # 1..3 chasing dots
        for i in range(n * 8):
            dots[i, 1] = 1

    return group, update


# ----------------------------------------------------------------------------
# Director: poll HA, switch scenes
# ----------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(description="HA-driven virtual LED matrix")
    parser.add_argument("--width", type=int, default=64, help="matrix width in pixels")
    parser.add_argument("--height", type=int, default=64, help="matrix height in pixels")
    parser.add_argument("--scale", type=int, default=8, help="screen px per LED")
    args = parser.parse_args()

    ha = MockHA(dwell=9.0)
    rain_group, rain_update = make_rain_scene(args.width, args.height)
    washer_group, washer_update = make_washer_scene(args.width, args.height)

    from fish_tank import create_scene as create_tank
    tank_group, tank_update = create_tank(args.width, args.height)

    display = vm.VirtualDisplay(args.width, args.height, scale=args.scale,
                                title="HA status -- virtual %dx%d" % (args.width, args.height))
    current = {"name": None}

    def show(name, group):
        if current["name"] != name:
            print("mode ->", name)
            display.show(group)
            current["name"] = name

    def update(dt):
        sensors = ha.poll(dt)
        if sensors["washer"] == "on":
            show("washer", washer_group)
            washer_update(dt)
        elif sensors["humidity"] >= 70:
            show("rain", rain_group)
            rain_update(dt, sensors["humidity"])
        else:
            show("tank", tank_group)
            tank_update(dt)

    update(0)
    display.run(update, fps=30)


if __name__ == "__main__":
    main()
