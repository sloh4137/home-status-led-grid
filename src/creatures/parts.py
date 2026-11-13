"""
Parts drawn on a spine creature: fins, tails, a snout, whiskers, and the
turtle's shell and flippers.

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

from math import atan2, ceil, cos, floor, pi, radians, sin, sqrt

import bitmaptools

from _dio import dio
from creatures.pattern import make_marks
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


class Flippers(Part):
    """
    The turtle's four flippers, paddling: a front and a rear pair around
    joint (the shell's centre), under the shell so it covers their roots.

    Each flipper is a short line of discs from its root, at (back, out) in
    base-body pixels from the joint, pointing angle degrees out from the
    tail direction. The angle swings by +-stroke over a paddle cycle, the
    diagonal pairs in step (front left with rear right), like a swimming
    turtle. The cycle advances with the distance the head moved, one cycle
    per stride px, so a pausing turtle holds its flippers still.

    Every phase is worked out on resize, so a frame only picks one and
    blits its discs, as BlobPart does.

    - front, rear: (back, out, length, angle, width) per pair. back is
      negative ahead of the joint. A pair with length 0 is left out.
    """

    under = True

    def __init__(
        self,
        joint=1,
        front=(-2.5, 3.5, 3.0, 100, 2.0),
        rear=(2.5, 3.0, 2.0, 40, 1.5),
        stroke=30,
        phases=6,
        stride=6.0,
    ):
        self.joint = joint
        self.front = front
        self.rear = rear
        self.stroke = stroke
        self.phases = phases
        self.stride = stride

    def _phase_blobs(self, creature, phase):
        """(back, out, diameter) for every disc at one phase of the cycle."""
        scale = creature.size / 100
        swing = cos(2 * pi * phase / self.phases)
        out = []
        for pair, sign_lead in ((self.front, 1), (self.rear, -1)):
            back, side, length, angle, width = pair
            if length <= 0:
                continue
            n = length * scale
            w = width * scale
            for side_sign in (1, -1):
                # Diagonal pairs in step: front left with rear right
                a = radians(angle + self.stroke * swing * sign_lead * side_sign)
                c = cos(a)
                s = sin(a)
                rb = back * scale
                rs = side * scale * side_sign
                for t, d in ((0.5, w), (1.0, w * 0.7)):
                    out.append((rb + n * t * c, rs + n * t * s * side_sign, d))
        return out

    def resize(self, state, creature):
        phases = []
        for p in range(self.phases):
            blobs = []
            for back, side, d in self._phase_blobs(creature, p):
                d = max(1, round(d))
                blobs.append((back, side, d / 2 - 0.5, stamps.disc(d, creature.fin_slot)))
            phases.append(tuple(blobs))
        travelled = 0.0 if state is None else state[2]
        # [joint, phases, distance the head has moved (Manhattan, no sqrt)]
        return [self.joint, tuple(phases), travelled]

    def reach(self, creature):
        best = 0
        for p in range(self.phases):
            for back, side, d in self._phase_blobs(creature, p):
                best = max(best, sqrt(back * back + side * side) + d / 2)
        return best + 1

    def render(self, state, creature, bitmap):
        travelled = state[2] + abs(creature._dx) + abs(creature._dy)
        state[2] = travelled
        phases = state[1]
        n = len(phases)
        blobs = phases[int(travelled * n / self.stride) % n]
        j = state[0]
        x = creature.jx[j]
        y = creature.jy[j]
        ax = creature.ux[j]
        ay = creature.uy[j]
        width = bitmap.width
        height = bitmap.height
        blit = bitmaptools.blit
        for back, side, o, disc in blobs:
            bx = floor(x - ax * back - ay * side - o)
            by = floor(y - ay * back + ax * side - o)
            if 0 <= bx < width and 0 <= by < height:
                blit(bitmap, disc, bx, by, skip_source_index=0)
            else:
                stamps.blit(bitmap, disc, bx, by)


class Shell(Part):
    """
    The turtle's shell: an oval rx by ry base-body pixels (half-lengths,
    rx along the heading) centred on joint, drawn over the body.

    It's pre-drawn, not built from discs: an oval only looks the same at any
    heading if it's round, so there's one sprite per heading (headings of
    them, evenly spaced) at the current size, and a frame does one atan2 at
    the joint and one blit. The look comes from the creature's variety
    (variety.shell, a ShellLook): the fill, a one-pixel rim, and the marks,
    placed by the creature's seed in shell coordinates (span from the front
    of the oval to the back, t across it) and baked into the sprites, so
    they turn with the shell at no extra cost.

    The sprites belong to the one creature (they hold its seeded marks), and
    resize rebuilds them on each size step.
    """

    def __init__(self, rx, ry, joint=1, headings=16):
        self.rx = rx
        self.ry = ry
        self.joint = joint
        self.headings = headings

    def resize(self, state, creature):
        look = creature.variety.shell
        if look is None:
            raise ValueError(
                "%s %s: a Shell needs variety.shell"
                % (creature.species.name, creature.variety.name)
            )
        scale = creature.size / 100
        ax = self.rx * scale
        ay = self.ry * scale
        marks = make_marks(look.marks, creature.seed)
        n = self.headings
        sprites = []
        for k in range(n):
            a = 2 * pi * k / n
            sprites.append(_draw_shell(ax, ay, cos(a), sin(a), look, marks))
        # Every sprite is the same size, centred on the joint's pixel
        return (self.joint, tuple(sprites), (sprites[0].width - 1) // 2)

    def reach(self, creature):
        return max(self.rx, self.ry) * creature.size / 100 + 1

    def render(self, state, creature, bitmap):
        j, sprites, c = state
        n = len(sprites)
        # The nearest pre-drawn heading; the +n keeps the index positive
        k = int(atan2(creature.uy[j], creature.ux[j]) * n / (2 * pi) + n + 0.5) % n
        stamps.blit(
            bitmap, sprites[k], floor(creature.jx[j]) - c, floor(creature.jy[j]) - c
        )


def _draw_shell(ax, ay, hx, hy, look, marks):
    """
    One shell sprite: an ax by ay oval (half-lengths, ax along the unit
    heading (hx, hy)) with a rim and the marks, centred in a square bitmap.
    """
    c = ceil(max(ax, ay) + 0.5)
    side = 2 * c + 1
    bitmap = dio.Bitmap(side, side, stamps.VALUES)
    inside = [[False] * side for _ in range(side)]
    for py in range(side):
        for px in range(side):
            dx = px - c
            dy = py - c
            # Into the shell's frame: u along the heading, v across it
            u = dx * hx + dy * hy
            v = dy * hx - dx * hy
            if (u / ax) ** 2 + (v / ay) ** 2 <= 1.05:
                inside[py][px] = True
    # Rim: inside pixels with a 4-neighbour outside
    rim = [[False] * side for _ in range(side)]
    for py in range(side):
        for px in range(side):
            if not inside[py][px]:
                continue
            for nx, ny in ((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1)):
                if not (0 <= nx < side and 0 <= ny < side) or not inside[ny][nx]:
                    rim[py][px] = True
                    break
            bitmap[px, py] = look.rim if rim[py][px] else look.fill
    # Marks inside the rim, like the body's spots: pct runs from the front of
    # the inner oval (u = +bx) to the back, and the offset across keeps the
    # disc inside it
    bx = max(0.5, ax - 1)
    by = max(0.5, ay - 1)
    for pct, t, radius, slot in marks:
        u = bx * (1 - pct / 50)
        half = by * sqrt(max(0, 1 - (u / bx) ** 2))
        d = max(1, min(round(radius * ay / 50), round(2 * half)))
        off = t / 100 * max(0, half - d / 2)
        mx = c + u * hx - off * hy
        my = c + u * hy + off * hx
        o = d / 2 - 0.5
        x0 = floor(mx - o)
        y0 = floor(my - o)
        dc = (d - 1) / 2
        r2 = (d / 2) ** 2 + 0.3
        for y in range(d):
            for x in range(d):
                if (x - dc) ** 2 + (y - dc) ** 2 > r2:
                    continue
                px = x0 + x
                py = y0 + y
                if 0 <= px < side and 0 <= py < side and inside[py][px] and not rim[py][px]:
                    bitmap[px, py] = slot
    return bitmap
