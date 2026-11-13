"""
The species table. A species is a data record, not a subclass: a new species
is one entry here, and only a new kind of part needs new code.

The save stores species by name, so the table can be reordered freely.
"""

from math import pi

from behaviors.flocking import Flock
from behaviors.wander import Wander
from creatures.parts import Fins, Tail


class Species:
    """
    Everything shared by the fish of one species. One instance per species,
    never mutated.

    - joints, link, widths: the spine. link is the distance between joints and
      widths the body width at each joint, both at size 100 (the base body).
    - angle_limit: the sharpest bend between consecutive joints, in radians.
    - color_variants, spots: the fixed color sets and the spot rule (M6).
    - parts: part instances (creatures/parts.py), drawn under or over the body. Each has
      attach(creature) -> state and render(state, creature, bitmap).
    - motion: a Flock or Wander record. The pond builds one behavior per
      species from it.
    - lifespan_days, size_min, size_cap, offspring_odds: the lifecycle (M9,
      M10). Sizes are percent of the base body.
    - lifecycle, persist: False for special fish that don't age or breed and
      aren't saved.
    """

    def __init__(
        self,
        name,
        joints,
        link,
        widths,
        angle_limit,
        motion,
        color_variants=(),
        spots=None,
        parts=(),
        lifespan_days=7,
        size_min=50,
        size_cap=100,
        offspring_odds=(),
        lifecycle=True,
        persist=True,
    ):
        if len(widths) != joints:
            raise ValueError(
                "%s: %d widths for %d joints" % (name, len(widths), joints)
            )
        self.name = name
        self.joints = joints
        self.link = link
        self.widths = widths
        self.angle_limit = angle_limit
        self.motion = motion
        self.color_variants = color_variants
        self.spots = spots
        self.parts = parts
        self.lifespan_days = lifespan_days
        self.size_min = size_min
        self.size_cap = size_cap
        self.offspring_odds = offspring_odds
        self.lifecycle = lifecycle
        self.persist = persist

    def __repr__(self):
        return "<Species %s>" % self.name


KOI = Species(
    name="koi",
    joints=10,
    link=4,
    widths=(8, 10, 10, 10, 9, 8, 6, 5, 3, 2),
    angle_limit=pi / 8,
    # Pectoral pair behind the head and a forked tail
    parts=(
        Fins(joint=1, length=4),
        Tail(length=5),
    ),
    motion=Flock(
        outside_window_size=30,
        wall_avoid_distance=30,
        perception_radius=10,
        fov_degrees=90,
        separation_force=50.0,
        alignment_force=5.0,
        cohesion_force=5.0,
        avoidance_force=100.0,
        random_steer=50,
        min_speed=1.0,
        max_speed=25.0,
        cruise_speed=20.0,
        cruise_force=2.0,
    ),
    lifespan_days=7,
    size_min=50,
    size_cap=110,
)

# The koi on WanderBehavior instead, for comparison (pond.KOI_WANDER)
KOI_WANDER = Wander(
    outside_window_size=30,
    wall_avoid_distance=30,
    avoidance_force=100.0,
    min_speed=1.0,
    max_speed=25.0,
    cruise_speed=20.0,
    max_turn=1.5,
    retarget=(1.0, 4.0),
)

SPECIES_BY_NAME = {s.name: s for s in (KOI,)}
