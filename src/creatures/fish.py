from creatures.spine import CreatureSpine
from graphics.vector import Vector
import math

from _dio import dio

FISH_PALETTE = [0x2E9BFF, 0xFFFFFF, 0x7FD4FF]
# Width of the fish at each vertabra
# BODY_WIDTH = [68, 81, 84, 83, 77, 64, 51, 38, 32, 19, 10, 10]
BODY_WIDTH = [8, 10, 10, 10, 9, 8, 6, 4, 4, 2, 1, 1]


class Fish(CreatureSpine):

    def __init__(self, origin: Vector, scale: float):
        super().__init__(origin, 12, math.ceil(8 * scale), math.pi / 8)
        self.scale = scale

        # Graphics
        self.palette = dio.Palette(4)
        self.palette.make_transparent(0)
        self.palette[1] = FISH_PALETTE[0]
        self.palette[2] = FISH_PALETTE[1]
        self.palette[3] = FISH_PALETTE[2]

        self.grid = dio.TileGrid(
            dio.Bitmap(1, 1, 256), pixel_shader=self.palette, x=0, y=0
        )
        self.render()

    def render_circle(self, center: Vector, radius: float, bitmap: dio.Bitmap):
        int_radius = math.ceil(radius)
        if int_radius <= 0:
            return

        x = math.floor(center.x)
        y = math.floor(center.y)

        # Let's just render squares for now
        for i in range(-int_radius, int_radius):
            for j in range(-int_radius, int_radius):
                ni, nj = x + i, y + j
                if 0 <= ni < bitmap.height and 0 <= nj < bitmap.width:
                    bitmap[ni, nj] = 1

    def render(self):
        """
        Render the fish parts including fins and tail
        """
        bitmap = dio.Bitmap(64, 64, 256)
        for i, vec in enumerate(self.joints):
            self.render_circle(vec, BODY_WIDTH[i] * self.scale, bitmap)

        self.grid.bitmap = bitmap
