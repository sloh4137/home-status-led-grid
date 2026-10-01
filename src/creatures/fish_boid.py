from math import atan2, floor, pi

from graphics.vector import Vector
from creatures.creature import Creature

import bitmaptools

from _dio import dio

# Triangle sprites for each of the 8 facing directions, indexed by octant clockwise (on screen,
# since y grows downward) starting from facing right. Rows are top to bottom as they appear on
# the display.
FACING_SPRITES = [
    ("X..", "XX.", "X.."),  # right
    ("..X", ".XX", "XXX"),  # down-right
    ("XXX", ".X.", "..."),  # down
    ("X..", "XX.", "XXX"),  # down-left
    ("..X", ".XX", "..X"),  # left
    ("XXX", "XX.", "X.."),  # up-left
    ("...", ".X.", "XXX"),  # up
    ("XXX", ".XX", "..X"),  # up-right
]

FACING_SPRITE_SINGLE = [
    ("...", ".X.", "X.."),  # right
    ("X..", ".X.", "..."),  # down-right
    (".X.", ".X.", "..."),  # down
    ("..X", ".X.", "..."),  # down-left
    ("...", ".XX", "..."),  # left
    ("...", ".X.", "..X"),  # up-left
    ("...", ".X.", ".X."),  # up
    ("...", ".X.", "X.."),  # up-right
]


def _sprite_bitmap(rows, color_index):
    # Only as many values as color_index needs. blit rejects a source with more bits
    # per value than the destination, and the destination holds color_index too.
    bitmap = dio.Bitmap(3, 3, color_index + 1)
    for y, row in enumerate(rows):
        for x, pixel in enumerate(row):
            bitmap[x, y] = color_index if pixel == "X" else 0
    return bitmap


# Facing sprites drawn in each palette index, built once and shared by every FishBoid
# of that color. render() blits the sprite for the current facing into the bitmap.
_facing_bitmaps = {}


def facing_bitmaps(color_index):
    bitmaps = _facing_bitmaps.get(color_index)
    if bitmaps is None:
        bitmaps = [_sprite_bitmap(rows, color_index) for rows in FACING_SPRITE_SINGLE]
        _facing_bitmaps[color_index] = bitmaps
    return bitmaps


class FishBoid(Creature):
    COLOR = 0xF54927

    def __init__(self, origin: Vector, color_index: int):
        """
        color_index is the palette index to draw with. Index 0 is skipped as
        transparent, so it must be at least 1.
        """
        # A single joint has no spine to solve, so position and velocity are kept as
        # plain floats instead of Vectors to avoid allocating on every update.
        self._x = origin.x
        self._y = origin.y
        self._vx = 0.0
        self._vy = 0.0
        self.facing = 0
        self.sprites = facing_bitmaps(color_index)

    def position(self) -> Vector:
        return Vector(self._x, self._y)

    @property
    def x(self) -> float:
        return self._x

    @property
    def y(self) -> float:
        return self._y

    @property
    def velocity(self) -> Vector:
        return Vector(self._vx, self._vy)

    def move(self, velocity: Vector):
        self.set_state(
            self._x + velocity.x, self._y + velocity.y, velocity.x, velocity.y
        )

    def set_state(self, x: float, y: float, vx: float, vy: float):
        self._x = x
        self._y = y
        self._vx = vx
        self._vy = vy

    def render(self, bitmap):
        """
        Render a triangle facing in the direction
        """
        vx = self._vx
        vy = self._vy
        # Keep the last facing when stopped, since atan2 of a zero vector is meaningless
        if vx * vx + vy * vy > 1e-18:
            self.facing = round(atan2(vy, vx) / (pi / 4)) % 8

        sprite = self.sprites[self.facing]
        # Offset by 1 so the center of the 3x3 sprite sits on the creature's position
        x = floor(self._x) - 1
        y = floor(self._y) - 1
        if x >= 0 and y >= 0:
            bitmaptools.blit(bitmap, sprite, x, y, skip_source_index=0)
            return

        # CircuitPython's blit rejects negative positions, so crop off the sprite's
        # columns/rows hanging past the left/top edge and blit the rest at 0
        x1 = -x if x < 0 else 0
        y1 = -y if y < 0 else 0
        if x1 < sprite.width and y1 < sprite.height:
            bitmaptools.blit(
                bitmap, sprite, x + x1, y + y1, x1=x1, y1=y1, skip_source_index=0
            )
