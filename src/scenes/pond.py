"""
Scene with procedural generated fish
"""

from _dio import dio
from creatures.spine import CreatureSpine
from creatures.fish import Fish
from creatures.fish_boid import FishBoid
from graphics.vector import Vector
from behaviors.circle import CircleBehavior
from behaviors.flocking import FlockingBehavior

import random


def create_scene(width=64, height=64):
    """
    Build the scene. Returns (group, update(dt)) for the main loop.
    """

    group = dio.Group()

    # chain = CreatureSpine(Vector(32, 32), num_joints=1, link_size=1)
    fish = Fish(Vector(32, 32), 0.25)
    creatures = [fish]
    circle_behavior = CircleBehavior(Vector(20, 20), 20, 100)
    circle_behavior.add_creatures(creatures)

    # Flocks
    boid_creatures = []
    for _ in range(100):
        boid_creatures.append(
            FishBoid(Vector(random.randrange(0, width), random.randrange(0, height)))
        )

    flock_behavior = FlockingBehavior(
        width,
        height,
        outside_window_size=30,
        wall_avoid_distance=10,
        perception_radius=5,
        fov_degrees=270,
        separation_force=50.0,
        alignment_force=5.0,
        cohesion_force=1.0,
        avoidance_force=200.0,
        min_speed=1.0,
        max_speed=50.0,
        cruise_speed=40.0,
        cruise_force=2.0,
    )
    flock_behavior.add_boids(boid_creatures)

    # for c in creatures:
    #     group.append(c.grid)

    for b in boid_creatures:
        group.append(b.grid)

    def update(dt):
        # circle_behavior.update(dt)
        flock_behavior.update(dt)

    return group, update
