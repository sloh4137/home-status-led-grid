"""
The species table. A species is a data record, not a subclass: a new species
is one entry here, and only a new kind of part needs new code.

The save stores species by name, so the table can be reordered freely.
"""

from math import pi

from behaviors.flocking import Flock
from behaviors.wander import Wander
from creatures.parts import Fins, Flippers, Shell, Snout, Tail, Whiskers
from creatures.varieties import (
    CATFISH_VARIETIES,
    KOI_VARIETIES,
    STURGEON_VARIETIES,
    TURTLE_VARIETIES,
)


class Species:
    """
    Everything shared by the fish of one species. One instance per species,
    never mutated.

    - joints, link, widths: the spine. link is the distance between joints and
      widths the body width at each joint, both at size 100 (the base body).
      A width of 0 draws no disc there (a joint a part covers).
    - angle_limit: the sharpest bend between consecutive joints, in radians.
    - varieties: the species' color varieties (creatures/varieties.py), at
      least one. A fish's genome names one of them.
    - parts: part instances (creatures/parts.py), drawn under or over the body. Each has
      attach(creature) -> state and render(state, creature, bitmap).
    - motion: a Flock or Wander record. The pond builds one behavior per
      species from it.
    - lifespan_days, size_min, size_cap, offspring_odds: the lifecycle (M9,
      M10). Sizes are percent of the base body.
    - lifecycle, persist: False for special fish that don't age or breed and
      aren't saved.
    - solo: exactly one at a time (the turtle). The lifecycle (M10) keeps it
      outside MAX_FISH, never breeds it, and replaces it with an egg when it
      dies. A solo species is never in anyone's offspring_odds.
    """

    def __init__(
        self,
        name,
        joints,
        link,
        widths,
        angle_limit,
        motion,
        varieties,
        parts=(),
        lifespan_days=7,
        size_min=50,
        size_cap=100,
        offspring_odds=(),
        lifecycle=True,
        persist=True,
        solo=False,
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
        if not varieties:
            raise ValueError("%s: no varieties" % name)
        self.motion = motion
        self.varieties = varieties
        self.parts = parts
        self.lifespan_days = lifespan_days
        self.size_min = size_min
        self.size_cap = size_cap
        self.offspring_odds = offspring_odds
        self.lifecycle = lifecycle
        self.persist = persist
        self.solo = solo

    def __repr__(self):
        return "<Species %s>" % self.name


KOI = Species(
    name="koi",
    joints=9,
    link=4,
    # widths=(8, 10, 10, 10, 9, 8, 6, 5, 3, 2),
    widths=(6, 8, 8, 8, 7, 6, 5, 3, 2),
    angle_limit=pi / 8,
    varieties=KOI_VARIETIES,
    # Pectoral pair behind the head and a forked tail
    parts=(
        Fins(joint=1, length=3),
        Tail(length=4),
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

# Wider than the koi, with a broad flat head, stubby fins and a short tail,
# and a pair of whiskers trailing from the mouth. Slow, with long pauses
# on the bottom.
CATFISH = Species(
    name="catfish",
    joints=9,
    link=3,
    widths=(9, 10, 10, 9, 7.5, 6, 4.5, 3, 1.5),
    angle_limit=pi / 7,
    varieties=CATFISH_VARIETIES,
    parts=(
        Fins(joint=1, length=1.5, sweep=70, width=1.5),
        Tail(length=2.25, spread=30),
        Whiskers(length=4.5),
    ),
    motion=Wander(
        outside_window_size=20,
        wall_avoid_distance=25,
        avoidance_force=60.0,
        min_speed=1.0,
        max_speed=12.0,
        cruise_speed=8.0,
        max_turn=1.0,
        retarget=(2.0, 5.0),
        pause_chance=0.25,
        # Follows the edges ~3/4 of the time (bouts of ~35 s), now and then
        # crossing the pond
        hug_distance=7,
        hug_chance=0.3,
        leave_chance=0.1,
    ),
    lifespan_days=10,
    size_min=50,
    size_cap=100,
)

# Long and narrow, with a pointed snout, long swept-back pectoral fins and a
# long tail. Stiff (small angle_limit) and on a low turn rate, so it swims in
# long, smooth curves.
STURGEON = Species(
    name="sturgeon",
    joints=12,
    link=3,
    widths=(4, 5, 6, 6, 6, 5, 5, 4, 4, 3, 2, 2),
    angle_limit=pi / 14,
    varieties=STURGEON_VARIETIES,
    parts=(
        Fins(joint=2, length=7, sweep=45, width=2),
        Fins(joint=7, length=3, sweep=40, width=2),
        Tail(length=6, spread=25),
        Snout(length=4),
    ),
    motion=Wander(
        # Close walls: on its low turn rate it would otherwise sail far off
        # screen before coming back
        outside_window_size=45,
        wall_avoid_distance=30,
        avoidance_force=80.0,
        min_speed=2.0,
        max_speed=18.0,
        cruise_speed=14.0,
        max_turn=0.6,
        retarget=(2.0, 6.0),
        turn_ease=1.0,
    ),
    lifespan_days=14,
    size_min=50,
    size_cap=130,
)

# A small head, the shell over the middle joint and a stub of a tail, with
# four paddling flippers. The shell is a pre-drawn sprite per heading
# (parts.Shell), so the whole turtle is about ten blits. About a quarter of
# the koi's speed, with long pauses. The loner of the pond: one at a time,
# never breeds (solo).
TURTLE = Species(
    name="turtle",
    joints=3,
    link=8,
    # Head and tail. The middle joint is under the shell, so it has no disc
    # (width 0) and neither link gets a gap fill: two body blits in all.
    widths=(4, 0, 2.5),
    angle_limit=pi / 5,
    varieties=TURTLE_VARIETIES,
    parts=(
        Flippers(joint=1, front=(-3.5, 4.5, 3.5, 100, 2.5), rear=(3.5, 4, 2.5, 40, 2)),
        Shell(rx=7, ry=5.5, joint=1),
    ),
    motion=Wander(
        outside_window_size=15,
        wall_avoid_distance=20,
        avoidance_force=40.0,
        min_speed=0.5,
        max_speed=8.0,
        cruise_speed=5.0,
        max_turn=0.8,
        retarget=(3.0, 8.0),
        pause_chance=0.4,
    ),
    lifespan_days=30,
    size_min=60,
    size_cap=90,
    solo=True,
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

# Every species, in draw order (bottom first): the bottom dwellers under the
# turtle, the koi on top
SPECIES = (CATFISH, STURGEON, TURTLE, KOI)
SPECIES_BY_NAME = {s.name: s for s in SPECIES}
