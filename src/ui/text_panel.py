"""Text overlay drawn as its own small layer on top of a scene.

The panel owns a width x (max_lines * LINE_HEIGHT + 1) bitmap with its own
3-color palette (index 0 transparent) and appends it to the scene's group as
the top layer. It only redraws when the text changes, so after that it never
marks the screen dirty, and a hidden panel costs nothing to composite.

Text is drawn straight over the scene with no backing box.
"""

from _dio import dio
from graphics.graphics_helpers import dim_palette, draw_text

LINE_HEIGHT = 6  # 5 px glyphs + 1 px gap

TRANSPARENT = 0
TEXT = 1
HIGHLIGHT = 2


def panel_height(max_lines):
    return max_lines * LINE_HEIGHT + 1


class TextPanel:
    def __init__(
        self,
        group,
        width,
        y,
        max_lines,
        text_color=0xFFFFFF,
        highlight_color=0xFFC020,
        brightness=0.35,
    ):
        self.width = width
        self.max_lines = max_lines
        self.bitmap = dio.Bitmap(width, panel_height(max_lines), 3)

        palette = dio.Palette(3)
        palette[TRANSPARENT] = 0x000000
        palette[TEXT] = text_color
        palette[HIGHLIGHT] = highlight_color
        # The panel's brightness is only on/off, so dim in the colors (like the pond)
        dim_palette(palette, brightness)
        palette.make_transparent(TRANSPARENT)

        self.grid = dio.TileGrid(self.bitmap, pixel_shader=palette, x=0, y=y)
        group.append(self.grid)

        self._lines = None
        self._highlight = None

    def set_lines(self, lines, highlight=None):
        """Show lines (top to bottom). highlight is the index of a line to draw
        in the highlight color, or None. No-op if nothing changed."""
        lines = tuple(lines[: self.max_lines])
        if lines == self._lines and highlight == self._highlight:
            return
        self._lines = lines
        self._highlight = highlight

        bitmap = self.bitmap
        bitmap.fill(TRANSPARENT)
        for i, line in enumerate(lines):
            if line:
                draw_text(
                    bitmap,
                    line,
                    1,
                    i * LINE_HEIGHT + 1,
                    HIGHLIGHT if i == highlight else TEXT,
                )

    @property
    def hidden(self):
        return self.grid.hidden

    @hidden.setter
    def hidden(self, value):
        self.grid.hidden = value
