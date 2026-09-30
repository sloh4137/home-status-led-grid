from math import atan2, floor, pi

from graphics.vector import Vector
from creatures.spine import CreatureSpine

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


class FishBoid(CreatureSpine):
    def __init__(self, origin: Vector):
        # A single joint has no spine to solve, so position and velocity are kept as
        # plain floats instead of Vectors to avoid allocating on every update.
        self._x = origin.x
        self._y = origin.y
        self._vx = 0.0
        self._vy = 0.0
        # Padding of 1 gives a 3x3 bitmap centered on the single joint
        super().__init__(origin, 1, 1, render_padding=1)
        self.facing = 0
        self.render()

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

    def make_palette(self):
        palette = dio.Palette(2)
        palette.make_transparent(0)
        palette[1] = 0xF54927
        return palette

    def render(self):
        """
        Render a triangle facing in the direction
        """
        vx = self._vx
        vy = self._vy
        if vx * vx + vy * vy > 1e-18:
            self.facing = round(atan2(vy, vx) / (pi / 4)) % 8

        sprite = FACING_SPRITES[self.facing]
        for y, row in enumerate(sprite):
            for x, pixel in enumerate(row):
                self.bitmap[x, y] = 1 if pixel == "X" else 0

        # Offset by 1 so the center of the 3x3 bitmap sits on the creature's position
        self.grid.x = floor(self._x) - 1
        self.grid.y = floor(self._y) - 1
