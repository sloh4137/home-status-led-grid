"""
Shared creature colors and the CO2 saturation shift.

The pond canvas shares the water sprite's 16-entry palette. The water uses
indices 0-5, so every creature color, across all species, lives in the slots
after it. Species refer to these slot numbers, never to RGB values, so a
saturation change is one palette write per slot with no per-creature cost.

The last RESERVED slots are for effects, not species. ELECTRIC (the
electric eel's flicker) is written every few frames while the eel is here,
through desaturate() so it goes gray with the rest. ZAP (the bolts and arcs
between boids) is a fixed color in EFFECT_RGB that PondColors rewrites with
the creature slots; the zaps flicker by frame, not by palette
(plans/ha-pond-effects.md).
"""

FIRST_SLOT = 6  # after the pond water's 0-5
PALETTE_SIZE = 16
RESERVED = 2
LAST_SLOT = PALETTE_SIZE - RESERVED - 1  # last slot a normal species may use

# Slot numbers. The koi varieties use WHITE..BRONZE; later species reuse
# them (sturgeon slate, catfish bronze). OLIVE took the spare slot 13 for
# the turtle's shell and skin, so every normal slot is now in use.
BOID = 6
WHITE = 7
RED = 8
BLACK = 9
GOLD = 10
SLATE = 11
BRONZE = 12
OLIVE = 13
# Reserved for effects
ELECTRIC = 14  # written every few frames by the eel's flicker
ZAP = 15  # fixed (EFFECT_RGB)

# (slot, base 0xRRGGBB) at full brightness
BASE_RGB = (
    (BOID, 0xF54927),
    # A warm white below max, so kohaku don't glare next to everything else
    (WHITE, 0xD8D0C0),
    (RED, 0xD81E10),
    # "Black" can't be palette black: an LED at 0 is off and a showa would
    # vanish. A dim charcoal just above the water (brightest ~0x101719)
    (BLACK, 0x2C2A2C),
    (GOLD, 0xE8A010),
    (SLATE, 0x5A7FA8),
    (BRONZE, 0x8A5422),
    (OLIVE, 0x5E7A2A),
)

# Effect slots with a fixed color, saturation-shifted like BASE_RGB. The
# zaps' main color: an electric yellow
EFFECT_RGB = ((ZAP, 0xFFFA05),)

# CO2 -> level: 0 (clean) at or below CO2_FULL ppm, rising linearly to
# MAX_LEVEL at or above CO2_DIM ppm, in whole steps. Every CO2 effect maps
# the level to its own range (saturation here, speed in the pond scene), so
# the thresholds live in one place.
CO2_FULL = 800
CO2_DIM = 2000
MAX_LEVEL = 10

# Level -> saturation step, in tenths: FULL_STEP in clean air, down to
# MIN_SATURATION_STEP at MAX_LEVEL. Not 0: a fully gray pond loses the
# difference between kohaku red and white, and between species.
FULL_STEP = 10
MIN_SATURATION_STEP = 2

# Gray the water with the creatures. A gray pond says "stale air" more
# clearly than gray fish in blue water. The water is very dim
# (POND_BRIGHTNESS), so if the shift bands or doesn't show on the panel,
# turn this off.
DESATURATE_WATER = True
WATER_SLOTS = range(FIRST_SLOT)


def _check():
    for slot, _ in BASE_RGB:
        if not FIRST_SLOT <= slot <= LAST_SLOT:
            raise ValueError(
                "creature color slot %d outside %d-%d" % (slot, FIRST_SLOT, LAST_SLOT)
            )


_check()


def desaturate(rgb, step):
    """
    rgb (0xRRGGBB) at step tenths (0-10) of full saturation: each channel
    moves toward the color's own luma, so it goes gray without changing much
    in brightness. Integer only; step FULL_STEP returns rgb unchanged.
    """
    r = (rgb >> 16) & 0xFF
    g = (rgb >> 8) & 0xFF
    b = rgb & 0xFF
    luma = (r * 77 + g * 150 + b * 29) >> 8
    # Floor division never overshoots: |(c - luma) * step // 10| <= |c - luma|
    r = luma + (r - luma) * step // FULL_STEP
    g = luma + (g - luma) * step // FULL_STEP
    b = luma + (b - luma) * step // FULL_STEP
    return (r << 16) | (g << 8) | b


def co2_level(values):
    """
    The CO2 level (0..MAX_LEVEL) for the sensor values dict
    ({key: (state, unit, t)}). Missing or unavailable CO2 -> 0 (clean).
    """
    entry = values.get("co2")
    if entry is None:
        return 0
    try:
        ppm = float(entry[0])
    except (TypeError, ValueError):  # "unavailable", "unknown", None
        return 0
    if ppm <= CO2_FULL:
        return 0
    if ppm >= CO2_DIM:
        return MAX_LEVEL
    # Round half up; round() rounds half to even, which makes the steps uneven
    return int(MAX_LEVEL * (ppm - CO2_FULL) / (CO2_DIM - CO2_FULL) + 0.5)


def saturation_step(level):
    """FULL_STEP at level 0, down to MIN_SATURATION_STEP at MAX_LEVEL."""
    span = FULL_STEP - MIN_SATURATION_STEP
    return FULL_STEP - (level * span + MAX_LEVEL // 2) // MAX_LEVEL


class PondColors:
    """
    Owns the pond palette's colors: installs the creature slots, remembers
    the water's (already dimmed) colors, and applies the CO2 saturation step
    from sensor values, writing the palette only when the step changes.
    The eel's flicker, which writes its slot every few frames, passes its
    colors through ``desaturate(rgb, colors.step)`` to match.
    """

    def __init__(self, palette, desaturate_water=DESATURATE_WATER):
        if len(palette) < PALETTE_SIZE:
            raise ValueError(
                "palette has %d entries, need %d" % (len(palette), PALETTE_SIZE)
            )
        self.palette = palette
        self.step = FULL_STEP
        # (slot, base rgb) for every slot the saturation shift rewrites
        base = list(BASE_RGB) + list(EFFECT_RGB)
        if desaturate_water:
            base = [(i, palette[i]) for i in WATER_SLOTS] + base
        self.base = tuple(base)
        self._write()

    def _write(self):
        palette = self.palette
        step = self.step
        for slot, rgb in self.base:
            palette[slot] = desaturate(rgb, step)

    def set_step(self, step):
        if step != self.step:
            self.step = step
            self._write()

    def set_sensors(self, values):
        self.set_step(saturation_step(co2_level(values)))
