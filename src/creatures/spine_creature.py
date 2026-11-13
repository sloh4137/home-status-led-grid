"""
The generic spine body: any species drawn from its data record.
"""

from math import ceil, floor

import bitmaptools

from creatures.pattern import make_spots
from creatures.spine import CreatureSpine
from graphics import stamps


class SpineCreature(CreatureSpine):
    """
    A fish built from its species: the spine and width profile come from the
    species, scaled by size (percent of the species' base body). The body is
    one pre-drawn disc per joint (graphics/stamps.py), so it keeps the same
    width at any heading and a frame does one native blit per joint.

    The variety (creatures/varieties.py) gives the body and fin colors and
    the marking layers; the seed places the markings (creatures/pattern.py),
    so the same seed always gives the same fish.

    Draw order is under parts (fins, tail), body, spots, then over parts. The
    parts are resolved here, so a frame does no per-species checks.
    """

    def __init__(self, species, origin, size, variety, seed):
        self.species = species
        self.variety = variety
        self.seed = seed
        self.size = 0
        # Palette slot the parts draw with
        self.fin_slot = variety.fins
        # Spots in body coordinates, [(joint, s, t, radius, slot)]; set_size
        # turns them into pixels in self.spot_stamps
        self.spots = make_spots(species, variety, seed)
        self.spot_stamps = ()
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
            color_index=variety.base,
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
        self.spot_stamps = self._place_spots(scale)
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

    def _place_spots(self, scale):
        """
        The spots at this size, as (joint, s, offset, o, disc): s is 0..1
        toward the next joint, offset the pixels out along the normal, and o
        the shift from the centre to the disc's corner. A disc is at most as
        wide as the body where it sits, and the offset is
        t * (half-width - radius), so even t = +-100 keeps the disc inside the
        outline and render never clips against the body.
        """
        widths = self.species.widths
        # The radius is percent of the widest half-width: 2 * r/100 * w/2
        widest = max(widths) * scale / 100
        out = []
        for joint, s, t, radius, slot in self.spots:
            f = s / 100
            half = (widths[joint] * (1 - f) + widths[joint + 1] * f) * scale / 2
            # Never wider than the body here, so a big patch on the narrow
            # tail doesn't spill out of the outline
            d = max(1, min(round(radius * widest), round(2 * half)))
            offset = t / 100 * max(0, half - d / 2)
            out.append((joint, f, offset, d / 2 - 0.5, stamps.disc(d, slot)))
        return tuple(out)

    def render(self, bitmap):
        """
        Draw the under parts, then a disc per joint sized by the species'
        widths (plus the gap-filling discs on the narrow tail), the spots,
        then the over parts.
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
        # Spots: lerp toward the next joint, then out along this joint's
        # normal (-uy, ux), so they bend with the spine
        ux = self.ux
        uy = self.uy
        for j, f, off, o, stamp in self.spot_stamps:
            x = jx[j]
            y = jy[j]
            cx = x + (jx[j + 1] - x) * f - uy[j] * off
            cy = y + (jy[j + 1] - y) * f + ux[j] * off
            x = floor(cx - o)
            y = floor(cy - o)
            if 0 <= x < width and 0 <= y < height:
                blit(bitmap, stamp, x, y, skip_source_index=0)
            else:
                stamps.blit(bitmap, stamp, x, y)
        for part, state in self.over:
            part.render(state, self, bitmap)
