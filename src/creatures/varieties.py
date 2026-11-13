"""
Color varieties: a base color, a fin color, and up to two marking layers, each
a (slot, zone) pair placed by creatures/pattern.py. A variety is pure data, so
a new one is one line in a species' tuple.

Each species has its own tuple (KOI_VARIETIES, later CATFISH_VARIETIES...).
Families and rarity weights only matter inside that tuple, so names only need
to be unique within a species.
"""

import random

from creatures.colors import BLACK, BRONZE, GOLD, RED, SLATE, WHITE
from creatures.pattern import DORSAL, EDGES, HEAD, PATCHES, SPECKS


class Variety:
    """
    - name: stored in the genome, unique within the species.
    - base, fins: palette slots (creatures/colors.py) for the body and parts.
    - layers: up to two (slot, Zone) pairs. Layer 2 is drawn over layer 1.
    - family: varieties that breed into each other (inherit_variety), or None.
    - weight: rarity, relative to the species' other varieties.
    """

    def __init__(self, name, base, fins, layers=(), family=None, weight=1):
        if len(layers) > 2:
            raise ValueError("%s: %d layers, max 2" % (name, len(layers)))
        self.name = name
        self.base = base
        self.fins = fins
        self.layers = layers
        self.family = family
        self.weight = weight

    def __repr__(self):
        return "<Variety %s>" % self.name


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

# inherit_variety tiers, in percent (tuned in M10)
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
    A child's variety from its parent's (a Variety of the same species):
    SAME % the parent's, FAMILY % another of its family by weight, NEW % any
    of the species by weight (which may roll the parent's again). A family
    of one, or no family, falls through FAMILY to SAME.
    """
    roll = random.randrange(100)
    if roll < SAME:
        return parent
    if roll < SAME + FAMILY:
        if parent.family is None:
            return parent
        family = [
            v
            for v in species.varieties
            if v.family == parent.family and v is not parent
        ]
        if not family:
            return parent
        return weighted_variety(family)
    return random_variety(species)
