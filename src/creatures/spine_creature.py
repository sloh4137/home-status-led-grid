"""
The generic spine body: any species drawn from its data record.
"""

from math import ceil, floor

import bitmaptools

from creatures.spine import CreatureSpine


class SpineCreature(CreatureSpine):
    """
    A fish built from its species: the spine and width profile come from the
    species, scaled by size (percent of the species' base body).

    Draw order is body, then parts. The parts are resolved here, so a frame
    does no per-species checks.
    """

    def __init__(self, species, origin, size, color_index):
        self.species = species
        self.size = 0
        super().__init__(
            origin,
            species.joints,
            ceil(species.link * size / 100),
            species.angle_limit,
            color_index=color_index,
        )
        self.set_size(size)
        # (part, per-creature state) pairs
        self.parts = [(part, part.attach(self)) for part in species.parts]

    def set_size(self, size):
        """
        Rescale the body to size percent: the link length, the half-width per
        joint, and the render bounds. Meant to be called on growth steps, not
        every frame.
        """
        if size == self.size:
            return
        self.size = size
        species = self.species
        scale = size / 100
        self.link_size = ceil(species.link * scale)
        # Half-width of the square drawn at each joint, precomputed so render
        # does no float math for it
        self.radii = [ceil(w * scale / 2) for w in species.widths]
        # No joint is further than the spine's length from the head, plus room
        # for the body width around the joints
        self.render_radius = (species.joints - 1) * self.link_size + ceil(
            max(species.widths) * scale
        )

    def render(self, bitmap):
        """
        Draw a square per joint, sized by the species' widths.
        """
        jx = self.jx
        jy = self.jy
        radii = self.radii
        color_index = self.color_index
        width = bitmap.width
        height = bitmap.height
        fill_region = bitmaptools.fill_region
        for i in range(len(jx)):
            r = radii[i]
            if r <= 0:
                continue
            x = floor(jx[i])
            y = floor(jy[i])
            # CircuitPython's fill_region rejects coordinates outside the
            # bitmap, so clamp the square to it.
            x1 = max(x - r, 0)
            y1 = max(y - r, 0)
            x2 = min(x + r, width)
            y2 = min(y + r, height)
            if x1 < x2 and y1 < y2:
                fill_region(bitmap, x1, y1, x2, y2, color_index)
        for part, state in self.parts:
            part.render(state, self, bitmap)
