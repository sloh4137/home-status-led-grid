"""
Scene with procedural generated fish
"""

from _dio import dio
from creatures.spine import CreatureSpine
from graphics.vector import Vector
from behaviors.circle import CircleBehavior


def create_scene(width=64, height=64):
    """
    Build the scene. Returns (group, update(dt)) for the main loop.
    """

    group = dio.Group()

    chain = CreatureSpine(Vector(32, 32), num_joints=1, link_size=1)
    creatures = [chain]
    circle_behavior = CircleBehavior(Vector(20, 20), 20, 100)
    circle_behavior.add_creatures(creatures)

    for c in creatures:
        group.append(c.grid)

    def update(dt):
        circle_behavior.update(dt)

    return group, update
