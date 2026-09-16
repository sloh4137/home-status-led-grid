"""Backend-agnostic graphics helpers for scenes.

Pure Python, operating on ``dio.Bitmap`` -- safe on real displayio and on the
simulator. (The copies in ``sim/virtual_matrix.py`` remain for backwards
compatibility; scenes should import from here.)
"""

from _dio import dio

# ----------------------------------------------------------------------------
# Tiny 3x5 pixel font (digits + % + a few letters) for sensor readouts
# ----------------------------------------------------------------------------

_FONT_3X5 = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "001", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    "%": ("101", "001", "010", "100", "101"),
    "H": ("101", "101", "111", "101", "101"),
    " ": ("000", "000", "000", "000", "000"),
}


def draw_text(bitmap, text, x, y, color_index, scale=1):
    """Draw 3x5 text into a bitmap.

    Bounds-checked: real displayio raises IndexError on out-of-range writes
    while the simulator silently clips, so the check lives here to keep both
    backends behaving the same.
    """
    cx = x
    for ch in text.upper():
        glyph = _FONT_3X5.get(ch, _FONT_3X5[" "])
        for gy, row in enumerate(glyph):
            for gx, pixel in enumerate(row):
                if pixel == "1":
                    for sy in range(scale):
                        for sx in range(scale):
                            px = cx + gx * scale + sx
                            py = y + gy * scale + sy
                            if 0 <= px < bitmap.width and 0 <= py < bitmap.height:
                                bitmap[px, py] = color_index
        cx += 4 * scale


def text_width(text, scale=1):
    return (len(text) * 4 - 1) * scale


# ----------------------------------------------------------------------------
# Sprite helpers
# ----------------------------------------------------------------------------

def bitmap_from_art(art, char_to_index):
    """Build a bitmap from a list of strings. '.' (or missing char) -> 0."""
    h = len(art)
    w = max(len(row) for row in art)
    bmp = dio.Bitmap(w, h, 256)
    for y, row in enumerate(art):
        for x, ch in enumerate(row):
            bmp[x, y] = char_to_index.get(ch, 0)
    return bmp


def flip_horizontal(bitmap):
    """Return a horizontally flipped copy of a bitmap."""
    out = dio.Bitmap(bitmap.width, bitmap.height, 256)
    for y in range(bitmap.height):
        for x in range(bitmap.width):
            out[bitmap.width - 1 - x, y] = bitmap[x, y]
    return out
