"""Ambient effects drawn over the boids. House power -> zaps between boids.

The house's total power sets a rate (zap_rate), and ZapEffect spends it on
two kinds of discharge, both drawn with a few ``bitmaptools.draw_line``
segments that follow their boids for their few frames:

- **Bolts** jump between a boid and its nearest flockmate. Each one plays
  BOLT_FRAMES: a thick jagged bolt in the ZAP color, a different bolt in
  white, a blank, then the first bolt again, thinner and breaking up over
  three more frames with a blank between, until it's gone. The blanks make
  it flicker.
- **Arcs** stay on a single boid: a small loop that leaves it and comes back,
  so the fish looks charged. They're rarer (ARC_CHANCE of the events) and
  short (ARC_FRAMES).

The colors are fixed palette slots (ZAP and WHITE) that the CO2 saturation
shift already rewrites (creatures/colors.py), so a frame writes no palette
entries. Lines cost ~0.2 ms each on the board (OPTIMIZATIONS.md M5.5), so the
shapes stay at 3-4 segments. A quiet house costs nothing.
"""

import random
from math import cos, log, pi, sin, sqrt

import bitmaptools

from creatures.colors import WHITE, ZAP

ZAP_MAX_RATE = 2.0  # zaps per second at or above ZAP_MAX_WATTS
# At most this many new zaps per frame, so a slow frame doesn't burst
MAX_NEW_ZAPS = 2
# A bolt only jumps to a flockmate within this many px
ZAP_REACH = 12
# Boids a zap tries before it gives up: the flocks roam past the edges, so
# a first pick is often off screen
SPAWN_TRIES = 3
# Share of the zap events that are arcs (loops on one boid) instead of bolts
ARC_CHANCE = 0.25

# A bolt has BOLT_BENDS sharp bends, alternating sides, BOLT_JAG px off the
# straight line at most (less for short bolts, which would look loopy)
BOLT_BENDS = 2
BOLT_SEGMENTS = BOLT_BENDS + 1
BOLT_JAG = (1.0, 2.5)
BOLT_JAG_FULL_LENGTH = 8.0  # bolts shorter than this jag proportionally less

# How a frame draws its segments
THIN = 0
THICK = 1  # each segment twice, the copy 1 px across
HALF = 2  # only the first half of each segment

# One entry per frame: None is a blank, else (shape, slot, keep, mode). shape
# 0 is the bolt's main shape, 1 its second (the white one). Each segment has
# a random rank, fixed for the bolt's life; a frame draws the segments ranked
# below keep, so the same parts go missing as it fades.
BOLT_FRAMES = (
    (0, ZAP, BOLT_SEGMENTS, THICK),
    (1, WHITE, BOLT_SEGMENTS, THIN),
    None,
    (0, ZAP, 2, THIN),
    None,
    (0, ZAP, 1, THIN),
    (0, ZAP, 1, HALF),
)

# An arc is a loop out of the boid and back: three points ARC_RADIUS px out,
# spread ARC_SPREAD radians either side of a random direction, the middle
# one a pixel further out.
ARC_SEGMENTS = 4
ARC_RADIUS = (2.5, 4.5)
ARC_SPREAD = 0.7
ARC_JITTER = 0.7
ARC_FRAMES = (
    (ZAP, ARC_SEGMENTS, THIN),
    (ZAP, 2, THIN),
)


def zap_rate(w, lo, hi):
    """Zaps per second for w watts of house power: 0 at or below lo, rising
    on a log scale to ZAP_MAX_RATE at hi, so each doubling looks like a
    similar step up. w None (unavailable) -> 0. A lo of 0 counts as 1 W."""
    if w is None or w <= lo:
        return 0.0
    if w >= hi:
        return ZAP_MAX_RATE
    lo = max(lo, 1)
    # max(): with lo at 0, under 1 W would go negative
    return max(0.0, ZAP_MAX_RATE * log(w / lo) / log(hi / lo))


def _ranks(n):
    """0..n-1 in random order (CircuitPython's random has no shuffle)."""
    ranks = list(range(n))
    for i in range(n - 1, 0, -1):
        j = random.randrange(i + 1)
        ranks[i], ranks[j] = ranks[j], ranks[i]
    return ranks


def _jag(side):
    """A bolt shape: BOLT_BENDS (t, offset) bends along the line, t the
    fraction of the way, offset px to the side (scaled by length when
    drawn), alternating sides from ``side`` so every bend is sharp."""
    uniform = random.uniform
    step = 1 / (BOLT_BENDS + 1)
    shape = []
    for k in range(1, BOLT_BENDS + 1):
        shape.append((k * step + uniform(-0.1, 0.1) * step, side * uniform(*BOLT_JAG)))
        side = -side
    return shape


def _segment(canvas, x0, y0, x1, y1, slot, mode, width, height):
    """One segment in slot, skipped if an end is off the canvas (the board's
    draw_line rejects out-of-range points)."""
    if mode == HALF:
        x1 = (x0 + x1) * 0.5
        y1 = (y0 + y1) * 0.5
    if not (
        0 <= x0 < width and 0 <= y0 < height and 0 <= x1 < width and 0 <= y1 < height
    ):
        return
    ix0 = int(x0)
    iy0 = int(y0)
    ix1 = int(x1)
    iy1 = int(y1)
    bitmaptools.draw_line(canvas, ix0, iy0, ix1, iy1, slot)
    if mode == THICK:
        # The copy goes 1 px across the segment's main direction
        if abs(ix1 - ix0) >= abs(iy1 - iy0):
            if iy0 + 1 < height and iy1 + 1 < height:
                bitmaptools.draw_line(canvas, ix0, iy0 + 1, ix1, iy1 + 1, slot)
        elif ix0 + 1 < width and ix1 + 1 < width:
            bitmaptools.draw_line(canvas, ix0 + 1, iy0, ix1 + 1, iy1, slot)


def _polyline(canvas, pts, ranks, keep, slot, mode, width, height):
    for s in range(len(ranks)):
        if ranks[s] < keep:
            x0, y0 = pts[s]
            x1, y1 = pts[s + 1]
            _segment(canvas, x0, y0, x1, y1, slot, mode, width, height)


class Bolt:
    """A bolt between boids a and b (the objects, not flock indices, so it
    follows them). Its shapes are relative to the a->b line, so they stretch
    and turn with the boids."""

    def __init__(self, a, b):
        self.a = a
        self.b = b
        self.frame = 0
        side = 1 if random.random() < 0.5 else -1
        # The white bolt bends the other way first, so it reads as new
        self.shapes = (_jag(side), _jag(-side))
        self.ranks = _ranks(BOLT_SEGMENTS)

    def draw(self, canvas, width, height):
        """Draw this frame and advance. False once it's over."""
        spec = BOLT_FRAMES[self.frame]
        self.frame += 1
        if spec is not None:
            shape, slot, keep, mode = spec
            ax = self.a.x
            ay = self.a.y
            dx = self.b.x - ax
            dy = self.b.y - ay
            d = sqrt(dx * dx + dy * dy)
            if d >= 1:
                # Unit perpendicular, scaled down for short bolts
                k = min(1.0, d / BOLT_JAG_FULL_LENGTH) / d
                px = -dy * k
                py = dx * k
                pts = [(ax, ay)]
                for t, off in self.shapes[shape]:
                    pts.append((ax + dx * t + px * off, ay + dy * t + py * off))
                pts.append((ax + dx, ay + dy))
                _polyline(canvas, pts, self.ranks, keep, slot, mode, width, height)
        return self.frame < len(BOLT_FRAMES)


class Arc:
    """A loop out of boid ``a`` and back, following it."""

    def __init__(self, a):
        self.a = a
        self.frame = 0
        uniform = random.uniform
        angle = uniform(0, 2 * pi)
        r = uniform(*ARC_RADIUS)
        self.offsets = [
            (
                cos(angle + da) * rr + uniform(-ARC_JITTER, ARC_JITTER),
                sin(angle + da) * rr + uniform(-ARC_JITTER, ARC_JITTER),
            )
            for da, rr in ((-ARC_SPREAD, r), (0, r + 1), (ARC_SPREAD, r))
        ]
        self.ranks = _ranks(ARC_SEGMENTS)

    def draw(self, canvas, width, height):
        slot, keep, mode = ARC_FRAMES[self.frame]
        self.frame += 1
        x = self.a.x
        y = self.a.y
        pts = [(x, y)]
        for ox, oy in self.offsets:
            pts.append((x + ox, y + oy))
        pts.append((x, y))
        _polyline(canvas, pts, self.ranks, keep, slot, mode, width, height)
        return self.frame < len(ARC_FRAMES)


class ZapEffect:
    """
    Zaps over the boid flocks. ``set_rate(per_second)`` when the house power
    changes, ``update(dt)`` once per frame on the real dt (power use doesn't
    slow with the CO2), after the boids draw.
    """

    def __init__(self, canvas, flocks, width, height):
        self.canvas = canvas
        self.flocks = flocks
        self.width = width
        self.height = height
        self.rate = 0.0
        self.live = []
        self._due = 0.0  # zaps owed, from rate x dt

    def set_rate(self, rate):
        self.rate = rate
        if rate <= 0:
            self._due = 0.0

    def update(self, dt):
        if self.rate > 0:
            self._due += self.rate * dt
            new = 0
            while self._due >= 1 and new < MAX_NEW_ZAPS:
                # Spend a random amount around 1, so the timing is irregular
                # instead of a metronome, at the same average rate
                self._due -= random.uniform(0.5, 1.5)
                new += 1
                self._spawn()
            if self._due > MAX_NEW_ZAPS:  # don't bank a backlog
                self._due = MAX_NEW_ZAPS
        live = self.live
        if not live:
            return
        canvas = self.canvas
        width = self.width
        height = self.height
        done = False
        for zap in live:
            if not zap.draw(canvas, width, height):
                zap.a = None  # mark finished
                done = True
        if done:
            self.live = [z for z in live if z.a is not None]

    def _spawn(self):
        """One zap from a random on-screen boid (SPAWN_TRIES picks): an arc
        on it, or a bolt to its nearest flockmate in reach. No boid on
        screen or no flockmate in reach -> nothing (the zap is spent)."""
        flocks = self.flocks
        randrange = random.randrange
        for _ in range(SPAWN_TRIES):
            flock = flocks[randrange(len(flocks))]
            n = len(flock.creatures)
            if not n:
                continue
            i = randrange(n)
            if 0 <= flock.xs[i] < self.width and 0 <= flock.ys[i] < self.height:
                break
        else:
            return
        a = flock.creatures[i]
        if random.random() < ARC_CHANCE:
            self.live.append(Arc(a))
            return
        j = flock.nearest(i, ZAP_REACH)
        if j >= 0:
            self.live.append(Bolt(a, flock.creatures[j]))
