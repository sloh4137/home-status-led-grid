"""
Pre-drawn stamps: small bitmaps drawn once and blitted natively each frame,
so a frame does one bitmaptools.blit per stamp instead of Python per pixel or
per line (see OPTIMIZATIONS.md "M5.5").

Stamps hold palette slots directly (0 is transparent), so each color needs
its own copy. Every stamp is cached and shared, keyed by what it depends on.
"""

import bitmaptools

from _dio import dio

# A canvas is 16 colors (4 bits per value). blit rejects a source with more
# bits per value than the destination, so stamps use the same.
VALUES = 16

_discs = {}


def disc(diameter, slot):
    """
    A filled disc diameter px across, shared per (diameter, slot).
    """
    key = (diameter, slot)
    bitmap = _discs.get(key)
    if bitmap is None:
        bitmap = dio.Bitmap(diameter, diameter, VALUES)
        c = (diameter - 1) / 2
        # A little over the true radius, so small discs aren't diamonds
        r2 = (diameter / 2) ** 2 + 0.3
        for y in range(diameter):
            for x in range(diameter):
                if (x - c) * (x - c) + (y - c) * (y - c) <= r2:
                    bitmap[x, y] = slot
        _discs[key] = bitmap
    return bitmap


def blit(dest, stamp, x, y):
    """
    Blit stamp with its top-left corner at (x, y), skipping 0 (transparent)
    and clipped to dest. CircuitPython's blit rejects a position outside the
    destination but clips the source to its right and bottom edges, so only
    the left and top need cropping here.
    """
    if x >= 0 and y >= 0:
        if x < dest.width and y < dest.height:
            bitmaptools.blit(dest, stamp, x, y, skip_source_index=0)
        return
    x1 = -x if x < 0 else 0
    y1 = -y if y < 0 else 0
    x += x1
    y += y1
    if x1 < stamp.width and y1 < stamp.height and x < dest.width and y < dest.height:
        bitmaptools.blit(dest, stamp, x, y, x1=x1, y1=y1, skip_source_index=0)
