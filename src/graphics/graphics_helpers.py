"""Backend-agnostic graphics helpers for scenes.

Pure Python, operating on ``dio.Bitmap`` -- safe on real displayio and on the
simulator. (The copies in ``sim/virtual_matrix.py`` remain for backwards
compatibility; scenes should import from here.)
"""

from _dio import dio

# ----------------------------------------------------------------------------
# Tiny 3x5 pixel font for sensor readouts and menus. 4 px advance, so a
# 64 px wide panel fits 16 characters; 6 px line height fits 10 lines.
# Lowercase is drawn as uppercase; unknown characters draw as "?".
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
    "A": ("010", "101", "111", "101", "101"),
    "B": ("110", "101", "110", "101", "110"),
    "C": ("011", "100", "100", "100", "011"),
    "D": ("110", "101", "101", "101", "110"),
    "E": ("111", "100", "110", "100", "111"),
    "F": ("111", "100", "110", "100", "100"),
    "G": ("011", "100", "101", "101", "011"),
    "H": ("101", "101", "111", "101", "101"),
    "I": ("111", "010", "010", "010", "111"),
    "J": ("001", "001", "001", "101", "010"),
    "K": ("101", "101", "110", "101", "101"),
    "L": ("100", "100", "100", "100", "111"),
    "M": ("101", "111", "111", "101", "101"),
    "N": ("110", "101", "101", "101", "101"),
    "O": ("010", "101", "101", "101", "010"),
    "P": ("110", "101", "110", "100", "100"),
    "Q": ("010", "101", "101", "110", "011"),
    "R": ("110", "101", "110", "101", "101"),
    "S": ("011", "100", "010", "001", "110"),
    "T": ("111", "010", "010", "010", "010"),
    "U": ("101", "101", "101", "101", "111"),
    "V": ("101", "101", "101", "101", "010"),
    "W": ("101", "101", "111", "111", "101"),
    "X": ("101", "101", "010", "101", "101"),
    "Y": ("101", "101", "010", "010", "010"),
    "Z": ("111", "001", "010", "100", "111"),
    "%": ("101", "001", "010", "100", "101"),
    ".": ("000", "000", "000", "000", "010"),
    "-": ("000", "000", "111", "000", "000"),
    ":": ("000", "010", "000", "010", "000"),
    ">": ("100", "010", "001", "010", "100"),
    "<": ("001", "010", "100", "010", "001"),
    "/": ("001", "001", "010", "100", "100"),
    "\u00b0": ("010", "101", "010", "000", "000"),  # degree sign
    "?": ("111", "001", "011", "000", "010"),
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
        glyph = _FONT_3X5.get(ch, _FONT_3X5["?"])
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


def dim_palette(palette, brightness):
    """Scale every color in palette by brightness (0.0-1.0), in place.

    The MatrixPortal's display brightness is only on/off, so dimming is done
    in the colors themselves. Call once per palette -- calling again dims it
    further.
    """
    for i in range(len(palette)):
        color = palette[i]
        r = int(((color >> 16) & 0xFF) * brightness)
        g = int(((color >> 8) & 0xFF) * brightness)
        b = int((color & 0xFF) * brightness)
        palette[i] = (r << 16) | (g << 8) | b


def make_canvas(group, width, height, palette):
    """
    Append a full-screen layer to group and return its bitmap, for the scene's
    background and creatures to render into.
    """
    bitmap = dio.Bitmap(width, height, len(palette))
    group.append(dio.TileGrid(bitmap, pixel_shader=palette))
    return bitmap
