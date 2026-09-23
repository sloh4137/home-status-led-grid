from math import floor, pi

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
        super().__init__(origin, 1, 1)
        self.facing = 0

        # Graphics
        self.palette = dio.Palette(2)
        self.palette.make_transparent(0)
        self.palette[1] = 0xF54927

        self.bitmap = dio.Bitmap(width=3, height=3, colors=256)
        self.grid = dio.TileGrid(
            self.bitmap, pixel_shader=self.palette, x=origin.x - 1, y=origin.y - 1
        )
        self.render()

    def render(self):
        """
        Render a triangle facing in the direction
        """
        if self.velocity.magnitude() > 1e-9:
            self.facing = round(self.velocity.heading() / (pi / 4)) % 8

        sprite = FACING_SPRITES[self.facing]
        for y, row in enumerate(sprite):
            for x, pixel in enumerate(row):
                self.bitmap[x, y] = 1 if pixel == "X" else 0

        # Offset by 1 so the center of the 3x3 bitmap sits on the creature's position
        self.grid.x = floor(self.x) - 1
        self.grid.y = floor(self.y) - 1
