"""
A lily pad with a tiny 3D printer on it: the visitor the printer's plug
calls in (scenes/visitors.py). Not a fish: no spine, no turning. It's one
pre-drawn sprite blitted centred on its position, in two frames with the
print head a pixel apart, swapped every FRAME_SECONDS so it's visibly
printing. Still one blit per frame.

The sprite uses existing palette slots only (creatures/colors.py), so it goes
gray with the CO2 saturation shift like everything else.
"""

from _dio import dio
from creatures import colors
from creatures.creature import Creature
from graphics import stamps
from graphics.vector import Vector

# The sprite, frame A. "." is transparent, "O" the pad, "K" the printer's
# frame (and its dark inside, so the bed and the print stand out), "S" the
# gantry, "H" the print head, "W" the bed and "P" the print. The notch is the
# wedge at the lower right.
ART = (
    "....OOOOO....",
    "..OOOOOOOOO..",
    ".OKKKKKKOOOO.",
    ".OKSHSSKOOOO.",
    "OOKKPPKKOOOOO",
    "OOKPPPPKOOOOO",
    "OOKWWWWKOOOOO",
    "OOKOOOOKO.OOO",
    "OOOOOOOOO..OO",
    ".OOOOOOOOO...",
    ".OOOOOOOOOO..",
    "..OOOOOOOOO..",
    "....OOOOO....",
)
# Frame B: the head one pixel to the right
HEAD_ROW = 3
ART_B = ART[:HEAD_ROW] + (".OKSSHSKOOOO.",) + ART[HEAD_ROW + 1 :]
FRAME_SECONDS = 0.5

SLOTS = {
    "O": colors.OLIVE,
    "K": colors.BLACK,
    "S": colors.SLATE,
    "H": colors.WHITE,
    "W": colors.WHITE,
}
# The print's color, one per pad, picked on arrival
PRINT_SLOTS = (colors.RED, colors.GOLD)

# Print slot -> (frame A, frame B), drawn once and shared
_sprites = {}


def _draw(art, print_slot):
    bitmap = dio.Bitmap(len(art[0]), len(art), stamps.VALUES)
    for y, row in enumerate(art):
        for x, c in enumerate(row):
            if c == "P":
                bitmap[x, y] = print_slot
            elif c != ".":
                bitmap[x, y] = SLOTS[c]
    return bitmap


def sprites(print_slot):
    frames = _sprites.get(print_slot)
    if frames is None:
        frames = (_draw(ART, print_slot), _draw(ART_B, print_slot))
        _sprites[print_slot] = frames
    return frames


class LilyPad(Creature):
    # How far the sprite reaches from its centre along x or y (it's 13 px
    # square, centred), which is what the behavior's culling box checks
    render_radius = 7

    def __init__(self, position, print_slot=colors.RED):
        self._x = position.x
        self._y = position.y
        self.frames = sprites(print_slot)
        self.frame = 0
        self._t = 0.0
        # Top-left offset from the centre
        self.ox = len(ART[0]) // 2
        self.oy = len(ART) // 2

    def position(self):
        return Vector(self._x, self._y)

    @property
    def x(self):
        return self._x

    @property
    def y(self):
        return self._y

    def set_state(self, x, y, vx, vy):
        self._x = x
        self._y = y

    def tick(self, dt):
        """Advance the print head: swap frames every FRAME_SECONDS."""
        t = self._t + dt
        if t >= FRAME_SECONDS:
            t -= FRAME_SECONDS
            if t >= FRAME_SECONDS:  # a long frame; don't catch up
                t = 0.0
            self.frame ^= 1
        self._t = t

    def render(self, bitmap):
        stamps.blit(
            bitmap,
            self.frames[self.frame],
            int(self._x) - self.ox,
            int(self._y) - self.oy,
        )
