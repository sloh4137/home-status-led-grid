"""
The pond: the fish genomes, the creatures built from them, and one behavior
per species.

    pond = Pond.from_dict(saved_section, canvas, width, height)
    store.provide("pond", pond.to_dict)
    pond.update(dt)

``from_dict`` validates the saved section (creatures/genome.py); a missing
or unusable section gives a fresh pond. The pond is only built at startup,
since state edits are restart-only, so there is no live re-apply.

Aging, breeding, death and the turtle's egg come in M10; for now a fish's
size is set once from its age (Genome.size).
"""

import random

from creatures import genome as genomes_mod
from creatures.genome import random_genome
from creatures.species import CATFISH, KOI, SPECIES, STURGEON, TURTLE
from creatures.spine_creature import SpineCreature
from graphics.vector import Vector

# A fresh pond (no saved state): (species, count). Ages are random up to
# FRESH_MAX_AGE percent of the lifespan, so most start full grown and a few
# are still growing.
FRESH_POND = ((KOI, 3), (CATFISH, 1), (STURGEON, 1), (TURTLE, 1))
FRESH_MAX_AGE = 50


class Pond:
    def __init__(self, canvas, width, height, genomes, next_id, motions=None):
        """
        genomes: validated Genome records. motions optionally overrides a
        species' motion record ({species: Flock/Wander}), e.g. the koi on
        Wander for comparison.
        """
        self.canvas = canvas
        self.width = width
        self.height = height
        self.genomes = genomes
        self.next_id = next_id
        # True when the saved section was missing or had to be repaired, so
        # the caller should save the pond as it is now
        self.changed = False
        self._motions = motions or {}
        # {species: behavior}, and the same behaviors in draw order
        self._behaviors = {}
        self.behaviors = []
        # Genome id -> creature
        self.creatures = {}
        for g in genomes:
            self._add_creature(g)

    @classmethod
    def from_dict(cls, section, canvas, width, height, motions=None):
        loaded = genomes_mod.load(section)
        if loaded is None:
            pond = cls.fresh(canvas, width, height, motions)
        else:
            genomes, next_id, repaired = loaded
            pond = cls(canvas, width, height, genomes, next_id, motions)
            pond.changed = repaired
        return pond

    @classmethod
    def fresh(cls, canvas, width, height, motions=None):
        print("state: no saved pond; starting a fresh one")
        genomes = []
        for species, count in FRESH_POND:
            for _ in range(count):
                hours = species.lifespan_days * 24 * FRESH_MAX_AGE // 100
                genomes.append(
                    random_genome(species, len(genomes), random.randint(0, hours))
                )
        pond = cls(canvas, width, height, genomes, len(genomes), motions)
        pond.changed = True
        return pond

    def to_dict(self):
        """The ``pond`` section of the saved document."""
        return {
            "next_id": self.next_id,
            "fish": [g.to_dict() for g in self.genomes if g.species_record().persist],
        }

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

    def _add_creature(self, genome):
        species = genome.species_record()
        creature = SpineCreature(
            species,
            Vector(
                random.uniform(0, self.width - 1), random.uniform(0, self.height - 1)
            ),
            genome.size(),
            genome.variety_record(),
            genome.seed,
        )
        creature.genome = genome
        self.creatures[genome.id] = creature
        self._behavior(species).add([creature])
        return creature

    def update(self, dt):
        for behavior in self.behaviors:
            behavior.update(dt)
