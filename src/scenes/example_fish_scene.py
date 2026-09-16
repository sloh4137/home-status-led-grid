"""Fish tank scene: fish, bubbles, water gradient, swaying seaweed.

Backend-agnostic -- runs in the desktop simulator and on the MatrixPortal.

    group, update = create_scene(width, height)
    # per frame: update(dt)
"""

import math
import random

from _dio import dio
from graphics.graphics_helpers import bitmap_from_art, flip_horizontal

# ----------------------------------------------------------------------------
# Fish sprites: '.' transparent, 'b' body, 'e' eye, 't' tail.
# Two frames; the tail wags by alternating them.
# ----------------------------------------------------------------------------

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
    # (body, eye, tail)
    (0xFF7B1C, 0xFFFFFF, 0xFFD23F),  # clownfish orange
    (0x2E9BFF, 0xFFFFFF, 0x7FD4FF),  # blue tang
    (0xB45CFF, 0xFFFFFF, 0xE0A6FF),  # purple
]


def make_fish_palette(body, eye, tail):
    pal = dio.Palette(4)
    pal.make_transparent(0)
    pal[1] = body
    pal[2] = eye
    pal[3] = tail
    return pal


class Fish:
    def __init__(self, colors, y, speed, direction, width, height):
        cmap = {".": 0, "b": 1, "e": 2, "t": 3}
        bmp_a = bitmap_from_art(FISH_A, cmap)
        bmp_b = bitmap_from_art(FISH_B, cmap)
        if direction > 0:  # swimming right -> face right
            bmp_a = flip_horizontal(bmp_a)
            bmp_b = flip_horizontal(bmp_b)
        self.frames = [bmp_a, bmp_b]
        self.palette = make_fish_palette(*colors)
        self.grid = dio.TileGrid(bmp_a, pixel_shader=self.palette, x=0, y=y)
        self.width = width
        self.height = height
        self.y_base = y
        self.speed = speed
        self.direction = direction
        w = bmp_a.width
        self.x = random.uniform(-w - 5, width + 5)
        self.phase = random.uniform(0, 6.28)
        self.t = 0.0

    def update(self, dt):
        self.t += dt
        self.x += self.direction * self.speed * dt
        w = self.frames[0].width
        if self.direction < 0 and self.x < -w:
            self.x = self.width + random.uniform(0, 20)
            self.y_base = random.randint(6, self.height - 18)
        elif self.direction > 0 and self.x > self.width:
            self.x = -w - random.uniform(0, 20)
            self.y_base = random.randint(6, self.height - 18)
        # gentle vertical bob + tail wag
        self.grid.x = int(self.x)
        self.grid.y = int(self.y_base + math.sin(self.t * 2.2 + self.phase) * 3)
        self.grid.bitmap = self.frames[int(self.t * 6) % 2]


# ----------------------------------------------------------------------------
# Bubbles
# ----------------------------------------------------------------------------

class Bubbles:
    def __init__(self, width, height, count=14):
        self.width = width
        self.height = height
        self.palette = dio.Palette(2)
        self.palette.make_transparent(0)
        self.palette[1] = 0x9BDCFF
        self.items = []
        for _ in range(count):
            self.items.append(self._new(random.uniform(0, height)))

    def _new(self, y=None):
        bmp = dio.Bitmap(3, 3, 2)
        for (x, yy) in [(1, 0), (0, 1), (2, 1), (1, 2)]:
            bmp[x, yy] = 1
        fy = float(y) if y is not None else float(self.height)
        return {
            "grid": dio.TileGrid(bmp, pixel_shader=self.palette,
                                 x=random.randint(0, self.width - 3),
                                 y=int(fy)),
            "fy": fy,
            "speed": random.uniform(8, 20),
            "wobble": random.uniform(0, 6.28),
        }

    def _respawn(self, b):
        b["grid"].x = random.randint(0, self.width - 3)
        b["fy"] = float(self.height + random.randint(0, 10))
        b["grid"].y = int(b["fy"])
        b["speed"] = random.uniform(8, 20)
        b["wobble"] = random.uniform(0, 6.28)

    def update(self, dt, t):
        for b in self.items:
            g = b["grid"]
            b["fy"] -= b["speed"] * dt
            g.y = int(b["fy"])
            g.x += int(math.sin(t * 3 + b["wobble"]) * 0.6)
            if b["fy"] < -4:
                self._respawn(b)


# ----------------------------------------------------------------------------
# Seaweed: precomputed sway frames at the bottom
# ----------------------------------------------------------------------------

def make_seaweed_frames():
    frames = []
    pal = dio.Palette(2)
    pal.make_transparent(0)
    pal[1] = 0x1FA84F
    for phase in range(4):
        bmp = dio.Bitmap(5, 18, 2)
        for y in range(18):
            x = 2 + int(math.sin(y * 0.45 + phase * 1.57) * 1.6)
            bmp[x, y] = 1
            if y > 12:  # little leaf nubs
                bmp[max(0, x - 1), y] = 1
        frames.append((bmp, pal))
    return frames


# ----------------------------------------------------------------------------
# Scene assembly
# ----------------------------------------------------------------------------

def make_water_background(width, height):
    """Vertical gradient, deep blue at top to slightly lighter at bottom."""
    pal = dio.Palette(16)
    pal[0] = 0x000000
    for i in range(1, 16):
        f = i / 15
        pal[i] = (int(4 + 10 * f) << 16) | (int(10 + 30 * f) << 8) | int(40 + 60 * f)
    bmp = dio.Bitmap(width, height, 16)
    for y in range(height):
        idx = 1 + int((y / height) * 14)
        for x in range(width):
            bmp[x, y] = idx
    return dio.TileGrid(bmp, pixel_shader=pal)


def create_scene(width=64, height=64):
    """Build the scene. Returns (group, update(dt)) for the main loop."""
    group = dio.Group()
    group.append(make_water_background(width, height))

    weed_frames = make_seaweed_frames()
    weeds = []
    for wx in (6, width // 2 - 2, width - 12):
        grid = dio.TileGrid(weed_frames[0][0], pixel_shader=weed_frames[0][1],
                            x=wx, y=height - 18)
        group.append(grid)
        weeds.append((grid, weed_frames, random.uniform(0, 4)))

    bubbles = Bubbles(width, height, count=14)
    for b in bubbles.items:
        group.append(b["grid"])

    fishes = [
        Fish(FISH_COLORS[0], y=max(4, height // 5), speed=14, direction=-1,
             width=width, height=height),
        Fish(FISH_COLORS[1], y=height // 2, speed=10, direction=1,
             width=width, height=height),
        Fish(FISH_COLORS[2], y=max(10, height * 2 // 3), speed=18, direction=-1,
             width=width, height=height),
    ]
    for f in fishes:
        group.append(f.grid)

    t = [0.0]

    def update(dt):
        t[0] += dt
        now = t[0]
        for f in fishes:
            f.update(dt)
        bubbles.update(dt, now)
        for grid, frames, phase in weeds:
            grid.bitmap = frames[int(now * 2 + phase) % 4][0]

    return group, update
