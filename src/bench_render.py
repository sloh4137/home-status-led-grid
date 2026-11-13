"""
Time one frame's drawing per species, split into body, spots and each part,
plus the spine update (set_state) and the pond water background. It answers
"where does the render time go" when DEBUG's render total grows.

On the board, stop code.py (Ctrl-C in the serial console), then at the REPL:

    import sys; sys.path.insert(0, "/src")
    import bench_render; bench_render.run()

On the desktop, from src/: python3 bench_render.py (desktop numbers don't
carry over to the board; Blinka's blit is pure Python).

Each fish is swum to the middle of the screen at size 100 first, so it's
fully on screen and nothing is clipped. Times are ms per call, averaged over
FRAMES calls.
"""

import time

from _dio import dio
from creatures.species import CATFISH, KOI, STURGEON
from creatures.spine_creature import SpineCreature
from creatures.varieties import find_variety
from graphics.vector import Vector

WIDTH = HEIGHT = 64
FRAMES = 50

# (species, variety): a plain and a spotted koi, both catfish looks with
# spots, and the sturgeon
CASES = (
    (KOI, "kohaku"),
    (KOI, "shusui"),
    (CATFISH, "plain"),
    (CATFISH, "mottled"),
    (STURGEON, "plain"),
)


def _ms(fn):
    t = time.monotonic_ns()
    for _ in range(FRAMES):
        fn()
    return (time.monotonic_ns() - t) / FRAMES / 1e6


def _fish(species, variety_name):
    """A fish swum diagonally into the middle of the screen."""
    variety = find_variety(species, variety_name)
    c = SpineCreature(species, Vector(8, 8), 100, variety, 1234)
    x = y = 8.0
    for _ in range(40):
        x += 0.6
        y += 0.6
        c.set_state(x, y, 0, 0)
    return c


def bench_fish(bm, species, variety_name):
    c = _fish(species, variety_name)
    under, over = c.under, c.over
    stamps = c.spot_stamps

    full = _ms(lambda: c.render(bm))
    c.under = c.over = ()
    no_parts = _ms(lambda: c.render(bm))
    c.spot_stamps = ()
    body = _ms(lambda: c.render(bm))
    c.under, c.over = under, over
    c.spot_stamps = stamps

    parts = []
    for part, state in list(under) + list(over):
        parts.append(
            (type(part).__name__, _ms(lambda: part.render(state, c, bm)))
        )

    # The spine update at swimming speed, as the behavior calls it
    pos = [c.jx[0], c.jy[0]]

    def step():
        pos[0] += 0.3
        pos[1] -= 0.3
        c.set_state(pos[0], pos[1], 0, 0)

    spine = _ms(step)

    name = "%s %s" % (species.name, variety_name)
    print(
        "%-16s full %5.2f | body %5.2f (%2d discs) | spots %5.2f (%2d) | spine %5.2f"
        % (
            name,
            full,
            body,
            len(c.discs) + len(c.fills),
            no_parts - body,
            len(stamps),
            spine,
        )
    )
    print("%16s parts: %s" % ("", ", ".join("%s %.2f" % p for p in parts)))


def bench_water():
    from scenes.pond import load_pond_water

    canvas = dio.Bitmap(WIDTH, HEIGHT, 16)
    _, _, draw = load_pond_water(WIDTH, HEIGHT)
    print("%-16s %5.2f" % ("pond water", _ms(lambda: draw(canvas))))


def run():
    bm = dio.Bitmap(WIDTH, HEIGHT, 16)
    print("ms per call, %d calls each" % FRAMES)
    for species, variety_name in CASES:
        bench_fish(bm, species, variety_name)
    bench_water()


if __name__ == "__main__":
    run()
