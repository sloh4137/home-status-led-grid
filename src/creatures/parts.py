"""
Parts drawn on a spine creature: fins, tails, and later whiskers or shells.

A part instance holds the settings shared by every fish of a species and
lives in the species table. Anything per fish comes from:

- attach(creature) -> state, when the creature is built, and
- resize(state, creature) -> state, on each size step (SpineCreature.set_size).
  Lengths are in base-body pixels, so the scaled values are worked out here
  and render does no scaling.
- render(state, creature, bitmap) draws it. Colors come from the creature
  (creature.fin_slot), so the part instance stays shared.
- reach(creature): how far past the spine the part can draw, in pixels, for
  the render culling bounds.

under = True parts are drawn before the body, so the body covers their roots.
"""

from math import ceil, cos, floor, radians, sin

import bitmaptools

from graphics import stamps


class Part:
    under = False

    def attach(self, creature):
        return self.resize(None, creature)

    def resize(self, state, creature):
        return state

    def reach(self, creature):
        return 0

    def render(self, state, creature, bitmap):
        pass


class BlobPart(Part):
    """
    A solid part made of filled discs placed around one joint, in the joint's
    own frame: each disc is (back, out, diameter), back along the tail
    direction and out along the normal. A disc looks the same at any heading,
    so nothing is pre-drawn per direction: a frame turns each offset with the
    joint's unit vector (a few multiplies, no trig) and blits a shared disc.

    Subclasses give joint_index(creature) and blobs(creature), the list of
    (back, out, diameter) at the creature's size.
    """

    under = True

    def joint_index(self, creature):
        raise NotImplementedError

    def blobs(self, creature):
        raise NotImplementedError

    def resize(self, state, creature):
        slot = creature.fin_slot
        out = []
        for back, side, d in self.blobs(creature):
            d = max(1, round(d))
            # Shift by half the disc so (back, side) is its centre
            out.append((back, side, d / 2 - 0.5, stamps.disc(d, slot)))
        return (self.joint_index(creature), tuple(out))

    def reach(self, creature):
        return max(
            (back * back + side * side) ** 0.5 + d / 2
            for back, side, d in self.blobs(creature)
        ) + 1

    def render(self, state, creature, bitmap):
        j, blobs = state
        x = creature.jx[j]
        y = creature.jy[j]
        ax = creature.ux[j]
        ay = creature.uy[j]
        width = bitmap.width
        height = bitmap.height
        blit = bitmaptools.blit
        for back, side, o, disc in blobs:
            # Centre = joint + back * (-a) + side * (-ay, ax)
            bx = floor(x - ax * back - ay * side - o)
            by = floor(y - ay * back + ax * side - o)
            if 0 <= bx < width and 0 <= by < height:
                blit(bitmap, disc, bx, by, skip_source_index=0)
            else:
                stamps.blit(bitmap, disc, bx, by)


class Fins(BlobPart):
    """
    A mirrored pair of solid fins at a spine joint. Each fin's root sits on
    the body edge at joint (inset by root_inset of the half-width, so the
    body covers it) and it points sweep degrees out from the tail direction.
    It's two discs along that line, a wider one near the root and a narrower
    one at the tip, which reads as a teardrop.
    """

    def __init__(self, joint, length, sweep=60, width=3, root_inset=0.8):
        self.joint = joint
        self.length = length
        self.sweep = sweep
        self.width = width
        self.root_inset = root_inset

    def joint_index(self, creature):
        return self.joint

    def blobs(self, creature):
        scale = creature.size / 100
        root = creature.radii[self.joint] * self.root_inset
        n = self.length * scale
        w = self.width * scale
        r = radians(self.sweep)
        c = cos(r)
        s = sin(r)
        out = []
        for side in (1, -1):
            # (fraction along the fin, diameter)
            for t, d in ((0.5, w), (1.0, w * 0.67)):
                out.append((n * t * c, (root + n * t * s) * side, d))
        return out


class Tail(BlobPart):
    """
    A forked tail from the last joint: two lobes spread degrees either side
    of the tail direction, each a line of shrinking discs. The last joint swings with the spine, so the tail sweeps on turns.
    """

    def __init__(self, length, spread=40, width=2):
        self.length = length
        self.spread = spread
        self.width = width

    def joint_index(self, creature):
        return len(creature.jx) - 1

    def blobs(self, creature):
        scale = creature.size / 100
        n = self.length * scale
        w = self.width * scale
        r = radians(self.spread)
        c = cos(r)
        s = sin(r)
        out = []
        for side in (1, -1):
            for t, d in ((0.4, w), (0.75, w), (1.0, w * 0.5)):
                out.append((n * t * c, n * t * s * side, d))
        return out
