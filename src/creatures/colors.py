"""
Shared creature colors and the CO2 brightness shift.

The pond canvas shares the water sprite's 16-entry palette. The water uses
indices 0-5, so every creature color, across all species, lives in the slots
after it. Species refer to these slot numbers, never to RGB values, so a
brightness change is one palette write per slot with no per-creature cost.

The last RESERVED slots are kept free for the future special fish and the
boid zaps (see plans/persistence-and-fish-variation.md "Future ideas").
"""

FIRST_SLOT = 6  # after the pond water's 0-5
PALETTE_SIZE = 16
RESERVED = 2
LAST_SLOT = PALETTE_SIZE - RESERVED - 1  # last slot a normal species may use

# Slot numbers. M6 replaces the single koi blue with the koi color variants.
BOID = 6
KOI_BLUE = 7

# (slot, base 0xRRGGBB) at full brightness
BASE_RGB = (
    (BOID, 0xF54927),
    (KOI_BLUE, 0x2E9BFF),
)

# CO2 -> brightness: full at or below CO2_FULL ppm, falling linearly to
# MIN_STEP tenths at or above CO2_DIM ppm, in whole tenths so the palette
# only changes when the step does.
CO2_FULL = 800
CO2_DIM = 2000
MIN_STEP = 4
FULL_STEP = 10


def _check():
    for slot, _ in BASE_RGB:
        if not FIRST_SLOT <= slot <= LAST_SLOT:
            raise ValueError("creature color slot %d outside %d-%d" % (slot, FIRST_SLOT, LAST_SLOT))


_check()


def set_brightness(palette, step):
    """
    Rewrite every creature slot from its base RGB at step tenths (0-10) of
    full brightness. About one palette write per slot.
    """
    for slot, rgb in BASE_RGB:
        r = ((rgb >> 16) & 0xFF) * step // FULL_STEP
        g = ((rgb >> 8) & 0xFF) * step // FULL_STEP
        b = (rgb & 0xFF) * step // FULL_STEP
        palette[slot] = (r << 16) | (g << 8) | b


def co2_step(values):
    """
    The brightness step (MIN_STEP..FULL_STEP tenths) for the sensor values
    dict ({key: (state, unit, t)}). Missing or unavailable CO2 -> full.
    """
    entry = values.get("co2")
    if entry is None:
        return FULL_STEP
    try:
        ppm = float(entry[0])
    except (TypeError, ValueError):  # "unavailable", "unknown", None
        return FULL_STEP
    if ppm <= CO2_FULL:
        return FULL_STEP
    if ppm >= CO2_DIM:
        return MIN_STEP
    span = FULL_STEP - MIN_STEP
    # Round half up; round() rounds half to even, which makes the steps uneven
    return FULL_STEP - int(span * (ppm - CO2_FULL) / (CO2_DIM - CO2_FULL) + 0.5)


class CreatureColors:
    """
    Owns the creature slots of one palette: installs them at full brightness
    and applies the CO2 step from sensor values, writing the palette only
    when the step changes.
    """

    def __init__(self, palette):
        if len(palette) < PALETTE_SIZE:
            raise ValueError("palette has %d entries, need %d" % (len(palette), PALETTE_SIZE))
        self.palette = palette
        self.step = FULL_STEP
        set_brightness(palette, FULL_STEP)

    def set_sensors(self, values):
        step = co2_step(values)
        if step != self.step:
            self.step = step
            set_brightness(self.palette, step)
