from creatures.spine import CreatureSpine
from graphics.vector import Vector
import math

import bitmaptools

from _dio import dio

FISH_PALETTE = [0x2E9BFF, 0xFFFFFF, 0x7FD4FF]
# Width of the fish at each vertabra
# BODY_WIDTH = [68, 81, 84, 83, 77, 64, 51, 38, 32, 19, 10, 10]
BODY_WIDTH = [8, 10, 10, 10, 9, 8, 6, 4, 4, 2, 1, 1]


class Fish(CreatureSpine):
    COLOR = FISH_PALETTE[0]

    def __init__(self, origin: Vector, scale: float, color_index: int):
        self.scale = scale
        super().__init__(
            origin,
            12,
            math.ceil(8 * scale),
            math.pi / 8,
            render_padding=math.ceil(max(BODY_WIDTH) * scale),
            color_index=color_index,
        )

    def render_circle(self, center: Vector, radius: float, bitmap: dio.Bitmap):
        int_radius = math.ceil(radius)
        if int_radius <= 0:
            return

        x = math.floor(center.x)
        y = math.floor(center.y)

        # Let's just render squares for now. CircuitPython's fill_region rejects
        # coordinates outside the bitmap, so clamp the square to it.
        x1 = max(x - int_radius, 0)
        y1 = max(y - int_radius, 0)
        x2 = min(x + int_radius, bitmap.width)
        y2 = min(y + int_radius, bitmap.height)
        if x1 < x2 and y1 < y2:
            bitmaptools.fill_region(bitmap, x1, y1, x2, y2, self.color_index)

    def render(self, bitmap):
        """
        Render the fish parts including fins and tail
        """
        for i, vec in enumerate(self.joints):
            self.render_circle(vec, BODY_WIDTH[i] * self.scale, bitmap)
