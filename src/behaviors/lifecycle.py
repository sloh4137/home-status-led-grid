"""
The pond: the fish genomes, the creatures built from them, one behavior per
species, and the lifecycle that ages, breeds and kills them.

    pond = Pond.from_dict(saved_section, canvas, width, height,
                          time_scale=pond_time_scale(settings),
                          on_change=store.mark_dirty)
    store.provide("pond", pond.to_dict)
    pond.update(dt)

``from_dict`` validates the saved section (creatures/genome.py); a missing
or unusable section gives a fresh pond. The pond is only built at startup,
since state edits are restart-only, so there is no live re-apply.

The lifecycle runs once per TICK_SECONDS of real time, not per frame, on a
clock sped up by ``time_scale`` (POND_TIME_SCALE). Ages are whole pond hours,
so nothing changes until a pond hour has passed; then, for each fish:

- it ages, and its body is rebuilt if it reached a new growth step;
- it dies at its death age (its lifespan +- 10 %, Genome.death_hours);
- otherwise, between BREED_START and BREED_END percent of its lifespan, with
  fewer than MAX_OFFSPRING births so far and fewer than MAX_FISH fish in the
  pond, it may breed (creatures/genome.py make_offspring), as long as the
  child's species is under its max_count. At most one birth per tick.

A solo species (the turtle) doesn't count toward MAX_FISH and never breeds.
When it dies it leaves an egg (a genome with a negative age) at a random spot
on screen, drawn as a small sprite outside any behavior. The egg ages like a
fish and at age 0 hatches into a new one with completely random stats.

Species with ``lifecycle=False`` don't age, breed or die, and don't count.
Every hour of aging, birth, death and hatching calls ``on_change``, so the
store saves the pond (at most once per PERSIST_SECONDS). Pond time short of
a whole hour isn't saved, so a restart loses up to an hour of it.
"""

import random

from _dio import dio
from creatures import colors
from creatures import genome as genomes_mod
from creatures.genome import MAX_OFFSPRING, egg, make_offspring, random_genome
from creatures.species import CATFISH, KOI, SPECIES, STURGEON, TURTLE
from creatures.spine_creature import SpineCreature
from graphics import stamps
from graphics.vector import Vector

# A fresh pond (no saved state): (species, count). Ages are random up to
# FRESH_MAX_AGE percent of the lifespan, so most start full grown and a few
# are still growing.
FRESH_POND = ((KOI, 3), (CATFISH, 1), (STURGEON, 1), (TURTLE, 1))
FRESH_MAX_AGE = 50

# Fish in the pond at most, not counting solo species (the turtle) or
# species without a lifecycle
MAX_FISH = 10

# Real seconds between lifecycle ticks
TICK_SECONDS = 1.0
HOUR = 3600

# A fish breeds between these percentages of its lifespan, on average
# BREED_TRIES times over that window if there's room (so most reach
# MAX_OFFSPRING when the pond isn't full)
BREED_START = 50
BREED_END = 90
BREED_TRIES = 6

# Pixels from the screen edge an egg is laid at least
EGG_INSET = 6
# The egg sprite: an off-white oval, "X" is the egg color
EGG_ART = (
    ".XX.",
    "XXXX",
    "XXXX",
    "XXXX",
    ".XX.",
)
EGG_SLOT = colors.WHITE

_egg_sprite = None


def egg_sprite():
    global _egg_sprite
    if _egg_sprite is None:
        bitmap = dio.Bitmap(len(EGG_ART[0]), len(EGG_ART), stamps.VALUES)
        for y, row in enumerate(EGG_ART):
            for x, c in enumerate(row):
                if c == "X":
                    bitmap[x, y] = EGG_SLOT
        _egg_sprite = bitmap
    return _egg_sprite


class Pond:
    def __init__(
        self,
        canvas,
        width,
        height,
        genomes,
        next_id,
        motions=None,
        time_scale=1,
        on_change=None,
    ):
        """
        genomes: validated Genome records. motions optionally overrides a
        species' motion record ({species: Flock/Wander}), e.g. the koi on
        Wander for comparison. time_scale speeds up the pond's clock;
        on_change() is called after every change worth saving.
        """
        self.canvas = canvas
        self.width = width
        self.height = height
        self.genomes = genomes
        self.next_id = next_id
        self.time_scale = time_scale
        self.on_change = on_change
        # True when the saved section was missing or had to be repaired, so
        # the caller should save the pond as it is now
        self.changed = False
        self._motions = motions or {}
        # {species: behavior}, and the same behaviors in draw order
        self._behaviors = {}
        self.behaviors = []
        # Genome id -> creature, and genome id -> (x, y) of each egg
        self.creatures = {}
        self.eggs = {}
        # Real seconds since the last lifecycle tick, and pond seconds short
        # of a whole hour
        self._clock = 0.0
        self._pond_seconds = 0.0
        for g in genomes:
            self._add(g)

    @classmethod
    def from_dict(cls, section, canvas, width, height, motions=None, **kwargs):
        loaded = genomes_mod.load(section)
        if loaded is None:
            pond = cls.fresh(canvas, width, height, motions, **kwargs)
        else:
            genomes, next_id, repaired = loaded
            pond = cls(canvas, width, height, genomes, next_id, motions, **kwargs)
            pond.changed = repaired
        return pond

    @classmethod
    def fresh(cls, canvas, width, height, motions=None, **kwargs):
        print("state: no saved pond; starting a fresh one")
        genomes = []
        for species, count in FRESH_POND:
            for _ in range(count):
                hours = species.lifespan_days * 24 * FRESH_MAX_AGE // 100
                genomes.append(
                    random_genome(species, len(genomes), random.randint(0, hours))
                )
        pond = cls(canvas, width, height, genomes, len(genomes), motions, **kwargs)
        pond.changed = True
        return pond

    def to_dict(self):
        """The ``pond`` section of the saved document."""
        return {
            "next_id": self.next_id,
            "fish": [g.to_dict() for g in self.genomes if g.species_record().persist],
        }

    def population(self):
        """Fish counted toward MAX_FISH."""
        n = 0
        for g in self.genomes:
            species = g.species_record()
            if species.lifecycle and not species.solo:
                n += 1
        return n

    def full_species(self):
        """Species at their max_count."""
        counts = {}
        for g in self.genomes:
            species = g.species_record()
            counts[species] = counts.get(species, 0) + 1
        return [
            s
            for s, n in counts.items()
            if s.max_count is not None and n >= s.max_count
        ]

    # ------------------------------------------------------------ members

    def _behavior(self, species):
        behavior = self._behaviors.get(species)
        if behavior is None:
            motion = self._motions.get(species, species.motion)
            behavior = motion.build(self.canvas, self.width, self.height)
            self._behaviors[species] = behavior
            # Keep draw order whatever order the species turn up in
            self.behaviors = [
                self._behaviors[s] for s in SPECIES if s in self._behaviors
            ]
        return behavior

    def _random_spot(self, inset=0):
        return (
            random.uniform(inset, self.width - 1 - inset),
            random.uniform(inset, self.height - 1 - inset),
        )

    def _add(self, genome, at=None):
        """Add the creature (or egg) for genome, at (x, y) or a random spot."""
        if genome.is_egg():
            if at is None:
                at = self._random_spot(EGG_INSET)
            self.eggs[genome.id] = (int(at[0]), int(at[1]))
            return None
        if at is None:
            at = self._random_spot()
        species = genome.species_record()
        creature = SpineCreature(
            species,
            Vector(at[0], at[1]),
            genome.size(),
            genome.variety_record(),
            genome.seed,
        )
        creature.genome = genome
        self.creatures[genome.id] = creature
        self._behavior(species).add([creature])
        return creature

    def _remove(self, genome):
        self.genomes.remove(genome)
        if genome.id in self.eggs:
            return self.eggs.pop(genome.id)
        creature = self.creatures.pop(genome.id)
        self._behaviors[genome.species_record()].remove(creature)
        return (creature.jx[0], creature.jy[0])

    def _new_id(self):
        id = self.next_id
        self.next_id += 1
        return id

    # ------------------------------------------------------------ lifecycle

    def update(self, dt):
        self._clock += dt
        if self._clock >= TICK_SECONDS:
            self.tick(self._clock * self.time_scale)
            self._clock = 0.0
        # Eggs lie on the bottom, under every fish
        if self.eggs:
            sprite = egg_sprite()
            for x, y in self.eggs.values():
                stamps.blit(self.canvas, sprite, x, y)
        for behavior in self.behaviors:
            behavior.update(dt)

    def tick(self, pond_seconds):
        """Advance the pond's clock; ages move in whole hours."""
        self._pond_seconds += pond_seconds
        hours = int(self._pond_seconds // HOUR)
        if hours:
            self._pond_seconds -= hours * HOUR
            self.age(hours)

    def age(self, hours):
        """Age every fish by hours, then grow, kill, hatch and breed them."""
        changed = False
        population = self.population()
        born = False
        for g in list(self.genomes):
            species = g.species_record()
            if not species.lifecycle:
                continue
            changed = True
            g.age_hours += hours
            if g.is_egg():
                continue
            if g.age_hours - hours < 0:
                self._hatch(g)
                continue
            if g.age_hours >= g.death_hours():
                self._die(g)
                if not species.solo:
                    population -= 1
                continue
            self._grow(g)
            if (
                not born
                and population < MAX_FISH
                and self._breeds(g, species, hours)
                and self._breed(g)
            ):
                population += 1
                born = True
        if changed and self.on_change:
            self.on_change()

    def _grow(self, genome):
        creature = self.creatures[genome.id]
        size = genome.size()
        if size != creature.size:
            creature.set_size(size)
            behavior = self._behaviors[genome.species_record()]
            behavior.render_margin = max(
                behavior.render_margin, creature.render_radius + 1
            )

    def _breeds(self, genome, species, hours):
        if species.solo or genome.offspring >= MAX_OFFSPRING:
            return False
        lifespan = genome.lifespan_hours()
        if not (
            lifespan * BREED_START <= genome.age_hours * 100 <= lifespan * BREED_END
        ):
            return False
        window = lifespan * (BREED_END - BREED_START) / 100
        return random.random() < BREED_TRIES * hours / window

    def _breed(self, parent):
        """Add a child of parent; False if its species is full."""
        result = make_offspring(parent, self.next_id, self.full_species())
        if result is None:
            return False
        child, tier = result
        self._new_id()
        parent.offspring += 1
        self.genomes.append(child)
        creature = self.creatures[parent.id]
        self._add(child, (creature.jx[0], creature.jy[0]))
        print(
            "pond: %s %d (%s, %s) born to %s %d"
            % (child.species, child.id, child.variety, tier, parent.species, parent.id)
        )
        return True

    def _die(self, genome):
        at = self._remove(genome)
        print(
            "pond: %s %d died at %d h" % (genome.species, genome.id, genome.age_hours)
        )
        species = genome.species_record()
        if species.solo:
            e = egg(species, self._new_id())
            self.genomes.append(e)
            self._add(e)
            print("pond: %s egg %d laid" % (species.name, e.id))

    def _hatch(self, genome):
        """The egg hatches in place into a new fish with random stats."""
        species = genome.species_record()
        at = self._remove(genome)
        child = random_genome(species, self._new_id())
        self.genomes.append(child)
        self._add(child, at)
        print(
            "pond: %s egg %d hatched into %s %d (%s, max %d)"
            % (species.name, genome.id, species.name, child.id, child.variety,
               child.max_size)
        )
