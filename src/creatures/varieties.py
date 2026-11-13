"""
Color varieties: a base color, a fin color, and up to two marking layers, each
a (slot, zone) pair placed by creatures/pattern.py. A variety is pure data, so
a new one is one line in a species' tuple.

Each species has its own tuple (KOI_VARIETIES, CATFISH_VARIETIES...).
Families and rarity weights only matter inside that tuple, so names only need
to be unique within a species.
"""

import random

from creatures.colors import BLACK, BRONZE, GOLD, OLIVE, RED, SLATE, WHITE
from creatures.pattern import (
    DORSAL,
    EDGES,
    HEAD,
    MOTTLE,
    PATCHES,
    SCUTES,
    SHELL_PLATES,
    SHELL_SPECKS,
    SPECKS,
)


class Variety:
    """
    - name: stored in the genome, unique within the species.
    - base, fins: palette slots (creatures/colors.py) for the body and parts.
    - layers: up to two (slot, Zone) pairs. Layer 2 is drawn over layer 1.
    - family: varieties that breed into each other (inherit_variety), or None.
    - weight: rarity, relative to the species' other varieties.
    - shell: a ShellLook for a species with a Shell part (the turtle), else
      None. The shell's markings live there, in shell coordinates; the
      body's layers are still drawn on the spine as usual.
    """

    def __init__(
        self, name, base, fins, layers=(), family=None, weight=1, shell=None
    ):
        if len(layers) > 2:
            raise ValueError("%s: %d layers, max 2" % (name, len(layers)))
        self.name = name
        self.base = base
        self.fins = fins
        self.layers = layers
        self.family = family
        self.weight = weight
        self.shell = shell

    def __repr__(self):
        return "<Variety %s>" % self.name


class ShellLook:
    """
    A turtle shell's colors: the fill, a one-pixel rim around the edge, and
    up to two (slot, Zone) marking layers placed on the oval by the seed
    (pattern.make_marks), all baked into the pre-drawn shell sprites.
    """

    def __init__(self, fill, rim, marks=()):
        if len(marks) > 2:
            raise ValueError("shell: %d mark layers, max 2" % len(marks))
        self.fill = fill
        self.rim = rim
        self.marks = marks


# Modelled on real koi; see the plan's variety table. The net/scale varieties
# are left out: their look is a pattern per scale, below one LED pixel.
KOI_VARIETIES = (
    Variety("kohaku", WHITE, WHITE, ((RED, PATCHES),), "gosanke", 10),
    Variety("sanke", WHITE, WHITE, ((RED, PATCHES), (BLACK, SPECKS)), "gosanke", 8),
    Variety("showa", BLACK, BLACK, ((RED, PATCHES), (WHITE, PATCHES)), "gosanke", 6),
    Variety("tancho", WHITE, WHITE, ((RED, HEAD),), "gosanke", 2),
    Variety("shiro utsuri", BLACK, BLACK, ((WHITE, PATCHES),), "utsuri", 5),
    Variety("hi utsuri", BLACK, BLACK, ((RED, PATCHES),), "utsuri", 4),
    Variety("ki utsuri", BLACK, BLACK, ((GOLD, PATCHES),), "utsuri", 3),
    Variety("asagi", SLATE, RED, ((RED, EDGES),), "blue", 4),
    Variety("shusui", SLATE, RED, ((RED, EDGES), (BLACK, DORSAL)), "blue", 3),
    Variety("hariwake", WHITE, WHITE, ((GOLD, PATCHES),), "metallic", 3),
    Variety("yamabuki ogon", GOLD, GOLD, (), "metallic", 4),
    Variety("platinum ogon", WHITE, WHITE, (), "metallic", 3),
    Variety("chagoi", BRONZE, BRONZE, (), "solid", 3),
)

# Catfish: plain is the common one, albino rare. One family, so a catfish
# breeds mostly true and now and then into another.
CATFISH_VARIETIES = (
    Variety("plain", BRONZE, BRONZE, (), "catfish", 10),
    Variety("mottled", BRONZE, BRONZE, ((BLACK, MOTTLE),), "catfish", 6),
    Variety("albino", WHITE, WHITE, (), "catfish", 1),
)

# Sturgeon: slate with the white rows of scutes. A single variety breeds true.
STURGEON_VARIETIES = (Variety("plain", SLATE, SLATE, ((WHITE, SCUTES),)),)

# Turtle: the body (head, tail, flippers) is plain skin and the look is in
# the shell. A turtle never breeds, so the family doesn't matter; the
# weights only pick the variety a new turtle hatches as.
TURTLE_VARIETIES = (
    # Olive shell with yellow scute centres and a dark rim (a slider)
    Variety(
        "slider",
        OLIVE,
        OLIVE,
        weight=6,
        shell=ShellLook(OLIVE, BLACK, ((GOLD, SHELL_PLATES),)),
    ),
    # Brown shell flecked with gold, slate skin (a box turtle)
    Variety(
        "box",
        SLATE,
        SLATE,
        weight=3,
        shell=ShellLook(BRONZE, BLACK, ((GOLD, SHELL_SPECKS),)),
    ),
    # Pale yellow shell, white skin: rare
    Variety("albino", WHITE, WHITE, weight=1, shell=ShellLook(GOLD, BRONZE)),
)

# inherit_variety tiers, in percent
SAME = 80
FAMILY = 15
NEW = 5


def find_variety(species, name):
    """The species' variety called name, or None."""
    for v in species.varieties:
        if v.name == name:
            return v
    return None


def weighted_variety(varieties):
    """One of varieties, picked by weight."""
    total = 0
    for v in varieties:
        total += v.weight
    roll = random.uniform(0, total)
    for v in varieties:
        roll -= v.weight
        if roll < 0:
            return v
    return varieties[-1]


def random_variety(species):
    """Any of the species' varieties, by weight."""
    return weighted_variety(species.varieties)


def inherit_variety(species, parent):
    """
    A child's variety from its parent's (a Variety of the same species), as
    (variety, tier): SAME % the parent's ("same"), FAMILY % another of its
    family by weight ("family"), NEW % any of the species by weight, which
    may roll the parent's again ("new"). A family of one, or no family,
    falls through FAMILY to SAME.
    """
    roll = random.randrange(100)
    if roll < SAME:
        return parent, "same"
    if roll < SAME + FAMILY:
        if parent.family is None:
            return parent, "same"
        family = [
            v
            for v in species.varieties
            if v.family == parent.family and v is not parent
        ]
        if not family:
            return parent, "same"
        return weighted_variety(family), "family"
    return random_variety(species), "new"
