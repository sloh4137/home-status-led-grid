"""
A fish's genome: everything that makes it this fish, saved in the ``pond``
section of the state document. Positions aren't saved; a restored fish
starts at a random spot.

    {"id": 3, "species": "koi", "variety": "sanke", "seed": 40213,
     "max_size": 92, "age_hours": 51, "offspring": 1}

Numbers are integers only: hand edits stay simple and dumps exact
(CircuitPython floats are 32-bit, so 0.92 could dump as 0.9200001). Species
and variety are stored by name, so their tables can be reordered.

Loading (``load``) validates each fish against the species table: a fish
with an unknown or missing species, or a duplicate id, is dropped; a bad or
missing field gets a default (a random variety or seed, a random size in
the species' range, age 0) or is clamped into range. Every drop, default
and clamp is printed on the serial console with the reason, and reported as
``repaired`` so the caller saves the fixed pond.
"""

import random

from creatures.species import SPECIES_BY_NAME
from creatures.varieties import find_variety, random_variety

SEED_MAX = 0xFFFF
MAX_OFFSPRING = 2

# Growth: a fish is born at GROWTH_START percent of its max size and reaches
# 100 % at GROWTH_DONE percent of its lifespan. The size changes in steps of
# GROWTH_STEP percent, so the body is only rebuilt a handful of times.
GROWTH_START = 30
GROWTH_DONE = 30
GROWTH_STEP = 10

FIELDS = ("id", "species", "variety", "seed", "max_size", "age_hours", "offspring")


class Genome:
    def __init__(self, id, species, variety, seed, max_size, age_hours=0, offspring=0):
        self.id = id
        # Names, as saved; species_record() and variety_record() look them up
        self.species = species
        self.variety = variety
        self.seed = seed
        # Percent of the species' base body, within [size_min, size_cap]
        self.max_size = max_size
        self.age_hours = age_hours
        self.offspring = offspring

    def __repr__(self):
        return "<Genome %d %s %s>" % (self.id, self.species, self.variety)

    def species_record(self):
        return SPECIES_BY_NAME[self.species]

    def variety_record(self):
        return find_variety(self.species_record(), self.variety)

    def growth(self):
        """Percent of max_size grown so far, in GROWTH_STEP steps."""
        return growth(self.age_hours, self.species_record().lifespan_days)

    def size(self):
        """The current body size, percent of the species' base body."""
        return max(1, self.max_size * self.growth() // 100)

    def to_dict(self):
        return {
            "id": self.id,
            "species": self.species,
            "variety": self.variety,
            "seed": self.seed,
            "max_size": self.max_size,
            "age_hours": self.age_hours,
            "offspring": self.offspring,
        }


def growth(age_hours, lifespan_days):
    """
    GROWTH_START percent at birth, rising linearly to 100 at GROWTH_DONE
    percent of the lifespan, then holding; rounded down to a GROWTH_STEP.
    Integer math, so both platforms give the same steps.
    """
    if age_hours <= 0:
        return GROWTH_START
    grown_hours = lifespan_days * 24 * GROWTH_DONE
    g = GROWTH_START + (100 - GROWTH_START) * age_hours * 100 // grown_hours
    if g >= 100:
        return 100
    return g - g % GROWTH_STEP


def random_genome(species, id, age_hours=0):
    """A fish with nothing inherited: a weighted random variety, a new seed
    and a max size anywhere in the species' range."""
    return Genome(
        id,
        species.name,
        random_variety(species).name,
        random.getrandbits(16),
        random.randint(species.size_min, species.size_cap),
        age_hours,
        0,
    )


# ---------------------------------------------------------------- loading
def _is_int(value):
    # bool is an int subclass, so rule it out explicitly
    return isinstance(value, int) and not isinstance(value, bool)


def _note(where, message):
    print("state: %s: %s" % (where, message))


def load(section):
    """
    The ``pond`` section -> (genomes, next_id, repaired), or None when there
    is no usable section (missing or not an object), meaning a fresh pond.
    An empty ``fish`` list is a valid, empty pond.
    """
    if section is None:
        return None
    if not isinstance(section, dict):
        _note("pond", "dropped %r (not an object)" % (section,))
        return None
    repaired = False
    next_id = section.get("next_id", 0)
    if not _is_int(next_id) or next_id < 0:
        _note("pond", "dropped next_id = %r (must be an integer >= 0)" % (next_id,))
        next_id = 0
        repaired = True
    fish = section.get("fish", [])
    if not isinstance(fish, list):
        _note("pond", "dropped fish = %r (not a list)" % (fish,))
        fish = []
        repaired = True
    for key in section:
        if key not in ("next_id", "fish"):
            _note("pond", "dropped %s (unknown key)" % key)
            repaired = True

    genomes = []
    ids = set()
    # Fish without an id get one after all the given ids are known, so a
    # hand-added fish never takes the id of a fish further down the list
    unnumbered = []
    for i, d in enumerate(fish):
        where = "pond.fish[%d]" % i
        result = _load_fish(d, where)
        if result is None:
            repaired = True
            continue
        genome, fixed = result
        repaired = repaired or fixed
        if genome.id is None:
            unnumbered.append((genome, where))
            continue
        if genome.id in ids:
            _note(where, "dropped (duplicate id %d)" % genome.id)
            repaired = True
            continue
        ids.add(genome.id)
        genomes.append(genome)
    if ids:
        next_id = max(next_id, max(ids) + 1)
    for genome, where in unnumbered:
        genome.id = next_id
        next_id += 1
        _note(where, "no id, given %d" % genome.id)
        genomes.append(genome)
    return genomes, next_id, repaired


def _load_fish(d, where):
    """One saved fish -> (Genome, repaired), or None if it can't be kept."""
    if not isinstance(d, dict):
        _note(where, "dropped %r (not an object)" % (d,))
        return None
    name = d.get("species")
    species = SPECIES_BY_NAME.get(name) if isinstance(name, str) else None
    if species is None:
        _note(where, "dropped (unknown species %r)" % (name,))
        return None
    if not species.persist:
        _note(where, "dropped (%s isn't saved)" % name)
        return None
    where = "%s %s" % (where, name)
    fixed = False
    for key in d:
        if key not in FIELDS:
            _note(where, "dropped %s (unknown key)" % key)
            fixed = True

    def bad(key, reason, default):
        nonlocal fixed
        fixed = True
        if key in d:
            _note(where, "dropped %s = %r (%s), using %r" % (key, d[key], reason, default))
        else:
            _note(where, "no %s, using %r" % (key, default))
        return default

    id = d.get("id")
    if not (_is_int(id) and id >= 0):
        # None: numbered by load() once every given id is known
        if "id" in d:
            _note(where, "dropped id = %r (must be an integer >= 0)" % (id,))
        id = None
        fixed = True

    variety = d.get("variety")
    if not (isinstance(variety, str) and find_variety(species, variety)):
        variety = bad(
            "variety",
            "not a %s variety" % name,
            random_variety(species).name,
        )

    seed = d.get("seed")
    if not (_is_int(seed) and 0 <= seed <= SEED_MAX):
        seed = bad("seed", "must be 0-%d" % SEED_MAX, random.getrandbits(16))

    lo, hi = species.size_min, species.size_cap
    max_size = d.get("max_size")
    if not _is_int(max_size):
        max_size = bad("max_size", "not an integer", random.randint(lo, hi))
    elif not lo <= max_size <= hi:
        clamped = max(lo, min(hi, max_size))
        _note(where, "max_size %d clamped to %d (%s: %d-%d)" % (max_size, clamped, name, lo, hi))
        max_size = clamped
        fixed = True

    age = d.get("age_hours")
    if not (_is_int(age) and age >= 0):
        age = bad("age_hours", "must be an integer >= 0", 0)

    offspring = d.get("offspring")
    if not (_is_int(offspring) and 0 <= offspring <= MAX_OFFSPRING):
        if _is_int(offspring):
            offspring = bad("offspring", "must be 0-%d" % MAX_OFFSPRING,
                            max(0, min(MAX_OFFSPRING, offspring)))
        else:
            offspring = bad("offspring", "must be 0-%d" % MAX_OFFSPRING, 0)
    if species.solo and offspring:
        offspring = bad("offspring", "a %s never breeds" % name, 0)

    return Genome(id, name, variety, seed, max_size, age, offspring), fixed
