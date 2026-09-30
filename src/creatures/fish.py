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
        self.scale = scale
        super().__init__(
            origin,
            12,
            math.ceil(8 * scale),
            math.pi / 8,
            render_padding=math.ceil(max(BODY_WIDTH) * scale),
        )
        self.render()

    def make_palette(self):
        palette = dio.Palette(4)
        palette.make_transparent(0)
        palette[1] = FISH_PALETTE[0]
        palette[2] = FISH_PALETTE[1]
        palette[3] = FISH_PALETTE[2]
        return palette

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
                if 0 <= ni < bitmap.width and 0 <= nj < bitmap.height:
                    bitmap[ni, nj] = 1

    def render(self):
        """
        Render the fish parts including fins and tail
        """
        self.update_grid_position()
        self.bitmap.fill(0)
        offset = Vector(self.grid.x, self.grid.y)
        for i, vec in enumerate(self.joints):
            self.render_circle(vec - offset, BODY_WIDTH[i] * self.scale, self.bitmap)
