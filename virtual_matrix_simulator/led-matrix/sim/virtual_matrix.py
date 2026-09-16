"""Virtual 64x64 RGB LED matrix for developing CircuitPython animations on a desktop.

The API mirrors CircuitPython's displayio (Bitmap, Palette, TileGrid, Group) so
animation code written against this simulator ports nearly 1:1 to the real
MatrixPortal -- just swap the import shim at the top of the example files.

On real hardware the equivalent setup is:
    import board, displayio, rgbmatrix, framebufferio
    matrix = rgbmatrix.RGBMatrix(width=64, height=64, bit_depth=4, ...)
    display = framebufferio.FramebufferDisplay(matrix, auto_refresh=True)
    display.show(group)

Requires tkinter (ships with CPython; on some Linux distros: apt install python3-tk).
"""

# ----------------------------------------------------------------------------
# displayio-compatible primitives
# ----------------------------------------------------------------------------

class Bitmap:
    """displayio.Bitmap: a width x height grid of palette indices."""

    def __init__(self, width, height, colors):
        self.width = width
        self.height = height
        self._pixels = bytearray(width * height)

    def __setitem__(self, pos, value):
        x, y = pos
        if 0 <= x < self.width and 0 <= y < self.height:
            self._pixels[y * self.width + x] = value & 0xFF

    def __getitem__(self, pos):
        x, y = pos
        if 0 <= x < self.width and 0 <= y < self.height:
            return self._pixels[y * self.width + x]
        return 0

    def fill(self, value):
        self._pixels = bytearray([value & 0xFF]) * (self.width * self.height)


class Palette:
    """displayio.Palette: maps a bitmap index to a 0xRRGGBB color."""

    def __init__(self, num_colors):
        self.colors = [0x000000] * num_colors
        self._transparent = set()

    def __setitem__(self, index, color):
        self.colors[index] = color

    def __getitem__(self, index):
        return self.colors[index]

    def make_transparent(self, index):
        self._transparent.add(index)

    def is_transparent(self, index):
        return index in self._transparent


class TileGrid:
    """displayio.TileGrid: places a Bitmap on screen at (x, y)."""

    def __init__(self, bitmap, pixel_shader, x=0, y=0):
        self.bitmap = bitmap
        self.pixel_shader = pixel_shader
        self.x = x
        self.y = y


class Group:
    """displayio.Group: ordered layers, drawn back-to-front."""

    def __init__(self):
        self._items = []

    def append(self, item):
        self._items.append(item)

    def remove(self, item):
        self._items.remove(item)

    def pop(self):
        return self._items.pop()

    def __len__(self):
        return len(self._items)

    def __iter__(self):
        return iter(self._items)


# ----------------------------------------------------------------------------
# Compositor: pure function, shared by the tkinter window and the GIF renderer
# ----------------------------------------------------------------------------

def composite(group, width, height):
    """Render a Group to a flat list of (r, g, b) tuples, row-major."""
    frame = [(0, 0, 0)] * (width * height)
    if group is None:
        return frame
    for layer in group:
        bmp = layer.bitmap
        pal = layer.pixel_shader
        ox, oy = int(layer.x), int(layer.y)
        for by in range(bmp.height):
            sy = oy + by
            if not 0 <= sy < height:
                continue
            for bx in range(bmp.width):
                sx = ox + bx
                if not 0 <= sx < width:
                    continue
                idx = bmp[bx, by]
                if pal.is_transparent(idx):
                    continue
                color = pal[idx]
                frame[sy * width + sx] = (
                    (color >> 16) & 0xFF,
                    (color >> 8) & 0xFF,
                    color & 0xFF,
                )
    return frame


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
    """Draw 3x5 text into a Bitmap. (On hardware, use adafruit_display_text.)"""
    cx = x
    for ch in text.upper():
        glyph = _FONT_3X5.get(ch, _FONT_3X5[" "])
        for gy, row in enumerate(glyph):
            for gx, pixel in enumerate(row):
                if pixel == "1":
                    for sy in range(scale):
                        for sx in range(scale):
                            bitmap[cx + gx * scale + sx, y + gy * scale + sy] = color_index
        cx += 4 * scale


def text_width(text, scale=1):
    return (len(text) * 4 - 1) * scale


# ----------------------------------------------------------------------------
# Sprite helpers
# ----------------------------------------------------------------------------

def bitmap_from_art(art, char_to_index):
    """Build a Bitmap from a list of strings. '.' (or missing char) -> 0."""
    h = len(art)
    w = max(len(row) for row in art)
    bmp = Bitmap(w, h, 256)
    for y, row in enumerate(art):
        for x, ch in enumerate(row):
            bmp[x, y] = char_to_index.get(ch, 0)
    return bmp


def flip_horizontal(bitmap):
    """Return a horizontally flipped copy of a Bitmap (for fish swimming right)."""
    out = Bitmap(bitmap.width, bitmap.height, 256)
    for y in range(bitmap.height):
        for x in range(bitmap.width):
            out[bitmap.width - 1 - x, y] = bitmap[x, y]
    return out


# ----------------------------------------------------------------------------
# The tkinter window
# ----------------------------------------------------------------------------

class VirtualDisplay:
    """A tkinter window pretending to be the LED panel.

    Each LED is drawn as a separate dot with a dark gap between pixels,
    like the real matrix -- not one continuous image.

    display.show(group)  -- like FramebufferDisplay.show()
    display.run(update)   -- calls update(dt) then redraws, at ~fps
    """

    def __init__(self, width=64, height=64, scale=8, title="Virtual LED Matrix"):
        import tkinter as tk

        self.width = width
        self.height = height
        self.scale = scale
        self._group = None
        self._last = [(0, 0, 0)] * (width * height)

        self._root = tk.Tk()
        self._root.title(title)
        self._canvas = tk.Canvas(
            self._root,
            width=width * scale,
            height=height * scale,
            bg="#0b0b0d",  # dark PCB-like background showing through the gaps
            highlightthickness=0,
        )
        self._canvas.pack()
        pad = max(1, scale // 6)
        self._dots = [
            [
                self._canvas.create_oval(
                    x * scale + pad, y * scale + pad,
                    (x + 1) * scale - pad, (y + 1) * scale - pad,
                    fill="#000000", outline="",
                )
                for x in range(width)
            ]
            for y in range(height)
        ]
        self._root.protocol("WM_DELETE_WINDOW", self._stop)
        self._running = True

    def show(self, group):
        self._group = group

    def refresh(self):
        frame = composite(self._group, self.width, self.height)
        for i, (rgb, last) in enumerate(zip(frame, self._last)):
            if rgb != last:
                y, x = divmod(i, self.width)
                self._canvas.itemconfig(
                    self._dots[y][x],
                    fill="#%02x%02x%02x" % rgb,
                )
        self._last = frame

    def run(self, update, fps=30):
        import time

        last = time.monotonic()

        def tick():
            nonlocal last
            if not self._running:
                return
            now = time.monotonic()
            dt = now - last
            last = now
            update(dt)
            self.refresh()
            self._root.after(int(1000 / fps), tick)

        tick()
        self._root.mainloop()

    def _stop(self):
        self._running = False
        self._root.destroy()
