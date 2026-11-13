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

from math import ceil, cos, floor, radians, sin, sqrt

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

    def slot(self, creature):
        """The palette slot the discs are drawn in: the fin color."""
        return creature.fin_slot

    def resize(self, state, creature):
        slot = self.slot(creature)
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
    It's two discs along that line (more on a long fin), a wider one near the
    root and a narrower one at the tip, which reads as a teardrop.
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
        # Two discs for a short fin; a long one gets one more per 2 px and
        # starts at most 2 px out, so it doesn't break up into dots or float
        # off the body. (fraction along the fin, diameter), from the first
        # disc at full width to the tip at two thirds of it.
        k = max(2, ceil(self.length / 2))
        t0 = min(0.5, 2 / self.length)
        steps = [
            (t0 + (1 - t0) * i / (k - 1), w * (1 - 0.33 * i / (k - 1)))
            for i in range(k)
        ]
        for side in (1, -1):
            for t, d in steps:
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


class Snout(BlobPart):
    """
    A pointed snout ahead of the head (the sturgeon's rostrum): a row of
    body-colored discs straight forward from joint 0, tapering from width to
    a single pixel. It's rigid, like a real snout, so it costs no spine
    joints, only a blit per disc.
    """

    def __init__(self, length, width=3, discs=3):
        self.length = length
        self.width = width
        self.discs = discs

    def joint_index(self, creature):
        return 0

    def slot(self, creature):
        return creature.color_index

    def blobs(self, creature):
        scale = creature.size / 100
        n = self.length * scale
        w = self.width * scale
        head = creature.radii[0]
        out = []
        for k in range(1, self.discs + 1):
            t = k / self.discs
            # back is negative: ahead of the joint, along the heading. The
            # first disc starts inside the head disc, so they join up.
            out.append((-(head * 0.5 + n * t), 0, max(1, w * (1 - t) + t)))
        return out


class Whiskers(Part):
    """
    A mirrored pair of barbels (the catfish's whiskers), drawn over the body
    as single pixels. Each one is a short follow-the-leader chain of length
    one-pixel links, rooted at the mouth: forward of joint 0 by forward, and
    out from the centre line by out, both fractions of the head's half-width.

    Each link points along a blend of where the chain trails (the way the
    link ahead dragged it) and the rest direction, spread degrees out from
    the tail direction, by stiffness. A still fish's whiskers settle at the
    rest shape, a moving one's are dragged back, and on a turn they swing
    the other way and trail, like the spine.

    The chain moves in render, the only per-frame hook a part has, so a fish
    off screen keeps its old whisker shape. Every link is placed exactly one
    link from the one ahead, so a stale chain never stretches; it just
    swings back into place over a few frames.
    """

    def __init__(self, length, spread=95, forward=0.5, out=0.8, stiffness=0.6):
        self.length = length
        self.spread = spread
        self.forward = forward
        self.out = out
        self.stiffness = stiffness

    def resize(self, state, creature):
        """
        State per fish: [forward px, out px, link px, xs, ys] with one chain
        per side, xs[side][k] / ys[side][k] for k = 0..length (0 = root).
        """
        scale = creature.size / 100
        head = creature.radii[0]
        # Links of about 1 px at size 100; length may be fractional
        links = max(1, round(self.length))
        if state is None:
            n = links + 1
            x = creature.jx[0]
            y = creature.jy[0]
            state = [0, 0, 0, ([x] * n, [x] * n), ([y] * n, [y] * n)]
            first = True
        else:
            first = False
        state[0] = head * self.forward
        state[1] = head * self.out
        state[2] = scale * self.length / links
        if first:
            # Lay the chains out at rest, so they don't unfold on frame one
            self._settle(state, creature, 1.0)
        return state

    def reach(self, creature):
        head = creature.radii[0]
        return (
            sqrt((head * self.forward) ** 2 + (head * self.out) ** 2)
            + self.length * creature.size / 100
            + 1
        )

    def _settle(self, state, creature, stiffness):
        fwd, out, link, xs, ys = state
        hx = creature.ux[0]
        hy = creature.uy[0]
        x0 = creature.jx[0] + hx * fwd
        y0 = creature.jy[0] + hy * fwd
        r = radians(self.spread)
        c = cos(r)
        s = sin(r)
        keep = 1 - stiffness
        pull = stiffness * link
        for side in (0, 1):
            sign = 1 if side == 0 else -1
            # Rest direction: back along -h, out along the normal (-hy, hx)
            rx = -hx * c - hy * s * sign
            ry = -hy * c + hx * s * sign
            px = xs[side]
            py = ys[side]
            x = x0 - hy * out * sign
            y = y0 + hx * out * sign
            px[0] = x
            py[0] = y
            for k in range(1, len(px)):
                # Where the link trails (from the link ahead to this one,
                # about link long), blended toward the rest direction
                dx = (px[k] - x) * keep + rx * pull
                dy = (py[k] - y) * keep + ry * pull
                d = sqrt(dx * dx + dy * dy)
                if d > 1e-9:
                    x += dx / d * link
                    y += dy / d * link
                else:
                    x += rx * link
                    y += ry * link
                px[k] = x
                py[k] = y

    def render(self, state, creature, bitmap):
        self._settle(state, creature, self.stiffness)
        slot = creature.fin_slot
        width = bitmap.width
        height = bitmap.height
        _, _, _, xs, ys = state
        for side in (0, 1):
            px = xs[side]
            py = ys[side]
            for k in range(len(px)):
                x = floor(px[k])
                y = floor(py[k])
                # Real displayio raises IndexError on out-of-range writes
                if 0 <= x < width and 0 <= y < height:
                    bitmap[x, y] = slot
