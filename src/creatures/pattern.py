"""
Spots: where a variety's marking colors go on the body.

A zone is a placement rule in body-relative units, shared by every species. A
variety (creatures/varieties.py) pairs zones with colors, and make_spots turns
the pair plus a seed into spots in body coordinates. SpineCreature.set_size
converts them to pixels on each size step, so a frame only blits.

A new pattern (another count, size or placement) is a new Zone record. A new
*kind* of pattern (stripes, bands) is a new mode branch in make_spots.

The spots come from a small integer xorshift, not random: CPython's and
CircuitPython's random give different sequences for the same seed, and this
gives the same spots on the desktop and the board. It also leaves the global
random alone. Everything make_spots returns is an integer for the same
reason (CircuitPython floats are 32-bit).
"""

SCATTER = "scatter"  # count spots at random within the span and t range
LINE = "line"  # count spots evenly spaced over the span, on each row of t


class Zone:
    """
    A placement rule.

    - count: spots, an int or an inclusive (lo, hi) range. For LINE, per row.
    - radius: spot radius in percent of the species' widest half-width, an
      int or (lo, hi), so the markings follow the body when its widths
      change, and scale with the fish's size. 0 is a single pixel at any
      size. A spot is never drawn wider than the body where it sits.
    - span: (lo, hi) percent of the body length, 0 = head, 100 = tail tip.
      Percent rather than joints, so a zone fits any joint count.
    - t: lateral position, percent of the half-width, -100..100 (the spot
      stays inside the outline even at +-100). SCATTER: an inclusive (lo, hi)
      range. LINE: a tuple of rows, e.g. (0,) down the back or (-100, 100)
      along both sides.
    - mode: SCATTER or LINE.
    - stagger: LINE only. Odd rows shift half a spacing along the body, so
      two rows read as alternating rather than paired.
    """

    def __init__(self, count, radius, span, t, mode=SCATTER, stagger=False):
        self.count = _range(count)
        self.radius = _range(radius)
        self.span = span
        self.t = t
        self.mode = mode
        self.stagger = stagger


def _range(v):
    return (v, v) if isinstance(v, int) else v


# Shared presets (see the plan's zone table). A species may add its own.
# Radii were tuned on a 10 px wide koi (half-width 5), where 20 % is 1 px.
PATCHES = Zone(count=(2, 4), radius=(40, 60), span=(0, 75), t=(-100, 100))
SPECKS = Zone(count=(2, 5), radius=20, span=(20, 75), t=(-100, 100))
HEAD = Zone(count=1, radius=40, span=(0, 0), t=(0, 0))
EDGES = Zone(count=7, radius=20, span=(10, 75), t=(-100, 100), mode=LINE, stagger=True)
DORSAL = Zone(count=4, radius=20, span=(10, 75), t=(0,), mode=LINE)

# Species-only zones
# Catfish: many small dark specks over the whole body
MOTTLE = Zone(count=(6, 10), radius=15, span=(0, 90), t=(-100, 100))
# Sturgeon: the three rows of bony plates (back and both sides) as dotted
# stripes. Radius 0 is a single pixel at any size, so the rows stay apart
# on the narrow body.
SCUTES = Zone(
    count=5, radius=0, span=(5, 85), t=(-100, 0, 100), mode=LINE, stagger=True
)


class XorShift:
    """
    16-bit xorshift (7, 9, 8), period 65535. Stays in small ints, so it's
    cheap on CircuitPython and identical on both platforms.
    """

    def __init__(self, seed):
        # 0 is the one stuck state; fold the seed so 0 is still valid
        s = (seed ^ 0xACE1) & 0xFFFF
        self.state = s or 0xACE1
        # Neighbouring seeds start close together; run a few steps apart
        for _ in range(4):
            self.next()

    def next(self):
        x = self.state
        x ^= (x << 7) & 0xFFFF
        x ^= x >> 9
        x ^= (x << 8) & 0xFFFF
        self.state = x
        return x

    def between(self, lo, hi):
        """An int in lo..hi inclusive."""
        if hi <= lo:
            return lo
        return lo + self.next() % (hi - lo + 1)


def _place(joints, pct):
    """
    Body percent -> (joint, s): the joint at or ahead of that point and s, 0-100
    percent of the way to the next joint. The last link ends at s = 100.
    """
    pos = pct * (joints - 1)  # in hundredths of a link
    joint = pos // 100
    if joint >= joints - 1:
        return joints - 2, 100
    return joint, pos % 100


def make_spots(species, variety, seed):
    """
    The variety's spots for this seed, in body coordinates:
    [(joint, s, t, radius, slot)], all ints. s is 0-100 percent of the way from
    joint to the next one, t is -100..100 percent of the half-width, and the
    radius is in percent of the widest half-width. Layer 1 comes first, so layer 2 is drawn on
    top of it.
    """
    rng = XorShift(seed)
    joints = species.joints
    spots = []
    for slot, zone in variety.layers:
        lo, hi = zone.span
        n = rng.between(zone.count[0], zone.count[1])
        r_lo, r_hi = zone.radius
        if zone.mode == SCATTER:
            t_lo, t_hi = zone.t
            for _ in range(n):
                joint, s = _place(joints, rng.between(lo, hi))
                spots.append(
                    (joint, s, rng.between(t_lo, t_hi), rng.between(r_lo, r_hi), slot)
                )
        elif zone.mode == LINE:
            # n spots per row, from lo to hi; a staggered row shifts by half
            # a spacing and drops its last spot so it stays inside the span
            step = (hi - lo) * 2 // (n - 1) if n > 1 else 0  # in half percent
            for row, t in enumerate(zone.t):
                shift = 1 if zone.stagger and row % 2 else 0
                for k in range(n - shift):
                    joint, s = _place(joints, lo + (step * k + step * shift // 2) // 2)
                    spots.append((joint, s, t, rng.between(r_lo, r_hi), slot))
        else:
            raise ValueError("unknown zone mode %r" % zone.mode)
    return spots
