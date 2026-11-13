from creatures.spine import CreatureSpine
from graphics.vector import Vector
import math

import bitmaptools

from _dio import dio

FISH_PALETTE = [0x2E9BFF, 0xFFFFFF, 0x7FD4FF]
# Width of the fish at each vertabra
# BODY_WIDTH = [68, 81, 84, 83, 77, 64, 51, 38, 32, 19, 10, 10]
BODY_WIDTH = [8, 10, 10, 10, 9, 8, 6, 4, 4, 2]


class Fish(CreatureSpine):
    COLOR = FISH_PALETTE[0]

    def __init__(self, origin: Vector, scale: float, color_index: int):
        self.scale = scale
        super().__init__(
            origin,
            10,
            math.ceil(4 * scale),
            math.pi / 8,
            render_padding=math.ceil(max(BODY_WIDTH) * scale),
            color_index=color_index,
        )

    def render(self, bitmap: dio.Bitmap):
        """
        Render the fish as a square per joint, sized by BODY_WIDTH.
        """
        jx = self.jx
        jy = self.jy
        scale = self.scale
        color_index = self.color_index
        width = bitmap.width
        height = bitmap.height
        fill_region = bitmaptools.fill_region
        for i in range(len(jx)):
            r = math.ceil(BODY_WIDTH[i] * scale / 2)
            if r <= 0:
                continue
            x = math.floor(jx[i])
            y = math.floor(jy[i])
            # Let's just render squares for now. CircuitPython's fill_region rejects
            # coordinates outside the bitmap, so clamp the square to it.
            x1 = max(x - r, 0)
            y1 = max(y - r, 0)
            x2 = min(x + r, width)
            y2 = min(y + r, height)
            if x1 < x2 and y1 < y2:
                fill_region(bitmap, x1, y1, x2, y2, color_index)
