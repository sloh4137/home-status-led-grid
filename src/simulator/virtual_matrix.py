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

from typing import Tuple, Union

# ----------------------------------------------------------------------------
# displayio-compatible primitives
# ----------------------------------------------------------------------------


class Bitmap:
    """displayio.Bitmap: a width x height grid of palette indices."""

    # Positional-only to match CircuitPython's displayio.Bitmap(width, height, value_count),
    # which doesn't take keyword arguments.
    def __init__(self, width: int, height: int, value_count: int, /):
        self.width = width
        self.height = height
        self._pixels = bytearray(width * height)

    # Like displayio, accepts either an (x, y) tuple or a flat row-major index
    # (adafruit_imageload writes pixels with the latter).
    def __setitem__(self, pos: Union[int, Tuple[int, int]], value):
        if isinstance(pos, int):
            if 0 <= pos < len(self._pixels):
                self._pixels[pos] = value & 0xFF
            return
        x, y = pos
        if 0 <= x < self.width and 0 <= y < self.height:
            self._pixels[y * self.width + x] = value & 0xFF

    def __getitem__(self, pos: Union[int, Tuple[int, int]]):
        if isinstance(pos, int):
            return self._pixels[pos] if 0 <= pos < len(self._pixels) else 0
        x, y = pos
        if 0 <= x < self.width and 0 <= y < self.height:
            return self._pixels[y * self.width + x]
        return 0

    def fill(self, value: int):
        self._pixels = bytearray([value & 0xFF]) * (self.width * self.height)


class Palette:
    """displayio.Palette: maps a bitmap index to a 0xRRGGBB color."""

    def __init__(self, num_colors: int):
        self.colors = [0x000000] * num_colors
        self._transparent = set()

    # Like displayio, accepts a 0xRRGGBB int or RGB bytes (as adafruit_imageload passes).
    def __setitem__(self, index: int, color: Union[int, bytes, bytearray]):
        if not isinstance(color, int):
            color = (color[0] << 16) | (color[1] << 8) | color[2]
        self.colors[index] = color

    def __getitem__(self, index: int) -> int:
        return self.colors[index]

    def __len__(self) -> int:
        return len(self.colors)

    def make_transparent(self, index: int):
        self._transparent.add(index)

    def is_transparent(self, index: int) -> bool:
        return index in self._transparent


class TileGrid:
    """displayio.TileGrid: places a Bitmap on screen at (x, y)."""

    def __init__(
        self,
        bitmap: Bitmap,
        pixel_shader: Palette,
        x: int = 0,
        y: int = 0,
        width: int = 1,
        height: int = 1,
        tile_width: int = None,
        tile_height: int = None,
        default_tile: int = 0,
    ):
        self._bitmap = bitmap
        self.pixel_shader = pixel_shader
        self.x = x
        self.y = y
        # Like displayio: a width x height grid of tiles, each tile_width x
        # tile_height, cut row-major from the bitmap (e.g. a sprite sheet).
        self.width = width
        self.height = height
        self.tile_width = tile_width or bitmap.width
        self.tile_height = tile_height or bitmap.height
        self._tiles = [default_tile] * (width * height)

    def __setitem__(self, pos: Union[int, Tuple[int, int]], tile: int):
        if not isinstance(pos, int):
            pos = pos[1] * self.width + pos[0]
        self._tiles[pos] = tile

    def __getitem__(self, pos: Union[int, Tuple[int, int]]) -> int:
        if not isinstance(pos, int):
            pos = pos[1] * self.width + pos[0]
        return self._tiles[pos]

    @property
    def bitmap(self) -> Bitmap:
        return self._bitmap

    @bitmap.setter
    def bitmap(self, bitmap: Bitmap):
        # Same check as displayio on hardware
        if bitmap.width != self._bitmap.width or bitmap.height != self._bitmap.height:
            raise ValueError("New bitmap must be same size as old bitmap")
        self._bitmap = bitmap


class Group:
    """displayio.Group: ordered layers, drawn back-to-front."""

    def __init__(self):
        self._items = []

    def append(self, item: TileGrid):
        self._items.append(item)

    def remove(self, item: TileGrid):
        self._items.remove(item)

    def pop(self) -> TileGrid:
        return self._items.pop()

    def __len__(self) -> int:
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
        tw, th = layer.tile_width, layer.tile_height
        tiles_per_row = bmp.width // tw
        for gy in range(layer.height):
            for gx in range(layer.width):
                tile = layer[gx, gy]
                src_x = (tile % tiles_per_row) * tw
                src_y = (tile // tiles_per_row) * th
                ox = int(layer.x) + gx * tw
                oy = int(layer.y) + gy * th
                for by in range(th):
                    sy = oy + by
                    if not 0 <= sy < height:
                        continue
                    for bx in range(tw):
                        sx = ox + bx
                        if not 0 <= sx < width:
                            continue
                        idx = bmp[src_x + bx, src_y + by]
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
                            bitmap[cx + gx * scale + sx, y + gy * scale + sy] = (
                                color_index
                            )
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
                    x * scale + pad,
                    y * scale + pad,
                    (x + 1) * scale - pad,
                    (y + 1) * scale - pad,
                    fill="#000000",
                    outline="",
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
