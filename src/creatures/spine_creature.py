"""
The generic spine body: any species drawn from its data record.
"""

from math import ceil, floor

import bitmaptools

from creatures.spine import CreatureSpine
from graphics import stamps


class SpineCreature(CreatureSpine):
    """
    A fish built from its species: the spine and width profile come from the
    species, scaled by size (percent of the species' base body). The body is
    one pre-drawn disc per joint (graphics/stamps.py), so it keeps the same
    width at any heading and a frame does one native blit per joint.

    Draw order is under parts (fins, tail), body, then over parts. The parts
    are resolved here, so a frame does no per-species checks.
    """

    def __init__(self, species, origin, size, color_index, fin_slot=None):
        self.species = species
        self.size = 0
        # Palette slot the parts draw with. Until varieties (M6) it's the body color.
        self.fin_slot = color_index if fin_slot is None else fin_slot
        # Per-creature part state, and (part, state) pairs split by layer.
        # Filled by set_size.
        self.part_states = None
        self.under = ()
        self.over = ()
        super().__init__(
            origin,
            species.joints,
            ceil(species.link * size / 100),
            species.angle_limit,
            color_index=color_index,
        )
        self.set_size(size)

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
        # Half-width of the body at each joint (parts attach to it)
        self.radii = [ceil(w * scale / 2) for w in species.widths]
        # A shared pre-drawn disc per joint, and the offset from the joint to
        # the disc's top-left corner, so render does one blit per joint
        diameters = [max(1, round(w * scale)) for w in species.widths]
        self.discs = [stamps.disc(d, self.color_index) for d in diameters]
        self.offsets = [d / 2 - 0.5 for d in diameters]
        # Joints whose disc is narrower than the link would leave a bead-like
        # gap to the joint ahead, so they get a second disc at the midpoint
        self.fills = [
            i for i in range(1, len(diameters)) if diameters[i] < self.link_size
        ]
        # The parts' scaled state. Built here rather than in __init__ because
        # it depends on the size; the first call attaches them.
        # part_states follows species.parts' order.
        parts = species.parts
        states = self.part_states
        if states is None:
            states = [part.attach(self) for part in parts]
        else:
            states = [part.resize(states[i], self) for i, part in enumerate(parts)]
        self.part_states = states
        self.under = [(p, s) for p, s in zip(parts, states) if p.under]
        self.over = [(p, s) for p, s in zip(parts, states) if not p.under]
        reach = 0
        for part in parts:
            reach = max(reach, part.reach(self))
        # No joint is further than the spine's length from the head, plus room
        # for the body width and the parts around the joints
        self.render_radius = (species.joints - 1) * self.link_size + ceil(
            max(max(species.widths) * scale, reach)
        )

    def render(self, bitmap):
        """
        Draw the under parts, then a disc per joint sized by the species'
        widths (plus the gap-filling discs on the narrow tail), then the over
        parts.
        """
        for part, state in self.under:
            part.render(state, self, bitmap)
        jx = self.jx
        jy = self.jy
        discs = self.discs
        offsets = self.offsets
        width = bitmap.width
        height = bitmap.height
        blit = bitmaptools.blit
        for i in range(len(jx)):
            stamp = discs[i]
            o = offsets[i]
            x = floor(jx[i] - o)
            y = floor(jy[i] - o)
            # Top-left on screen is the common case: straight to the native
            # blit, which clips the right and bottom itself
            if 0 <= x < width and 0 <= y < height:
                blit(bitmap, stamp, x, y, skip_source_index=0)
            else:
                stamps.blit(bitmap, stamp, x, y)
        for i in self.fills:
            stamp = discs[i]
            o = offsets[i]
            stamps.blit(
                bitmap,
                stamp,
                floor((jx[i - 1] + jx[i]) / 2 - o),
                floor((jy[i - 1] + jy[i]) / 2 - o),
            )
        for part, state in self.over:
            part.render(state, self, bitmap)
