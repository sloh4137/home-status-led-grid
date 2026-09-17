"""
Scene with procedural generated fish
"""

from _dio import dio
from creatures.chain import Chain
from creatures.vector import Vector
import math


def create_scene(width=64, height=64):
    """
    Build the scene. Returns (group, update(dt)) for the main loop.
    """

    group = dio.Group()

    chain = Chain(Vector(32, 32), 5, 3)

    group.append(chain.grid)

    t = [0.0]
    head_positions = [Vector(32, 32), Vector(32, 10), Vector(10, 10), Vector(10, 32)]

    def update(dt):
        t[0] += dt
        now = t[0]
        chain.move(head_positions[math.floor(now) % 4])
        chain.render()

    return group, update
