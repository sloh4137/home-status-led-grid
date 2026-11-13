"""
Time FlockingBehavior's neighbour search: the direct loop against the spatial
grid, for the koi flock at several sizes and for the background boids.

On the board, stop code.py (Ctrl-C in the serial console), then at the REPL:

    import sys; sys.path.insert(0, "/src")
    import bench_flock; bench_flock.run()

On the desktop, from src/: python3 bench_flock.py

Only physics is timed (steering + moving the creatures); rendering is switched
off, since it costs the same in both modes. "steer" is the flocking itself,
"total" adds the move loop and Creature.set_state (the koi spine).
"""

import random
import time

from _dio import dio
from behaviors.flocking import FlockingBehavior
from creatures.fish import Fish
from creatures.fish_boid import FishBoid
from graphics.vector import Vector

WIDTH = HEIGHT = 64
DT = 1 / 15
WARMUP = 10
FRAMES = 60


def koi_flock(canvas, n, grid, steer_half=True):
    flock = FlockingBehavior(
        canvas,
        WIDTH,
        HEIGHT,
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
        grid_min_boids=0 if grid else 10**6,
        steer_half=steer_half,
    )
    flock.add(
        [
            Fish(
                Vector(random.uniform(0, WIDTH), random.uniform(0, HEIGHT)),
                random.choice((0.5, 1)),
                6,
            )
            for _ in range(n)
        ]
    )
    return flock


def boid_flock(canvas, n, grid):
    flock = FlockingBehavior(
        canvas,
        WIDTH,
        HEIGHT,
        outside_window_size=30,
        wall_avoid_distance=30,
        perception_radius=5,
        fov_degrees=270,
        separation_force=25.0,
        alignment_force=5.0,
        cohesion_force=5.0,
        avoidance_force=200.0,
        random_steer=1,
        min_speed=1.0,
        max_speed=50.0,
        cruise_speed=40.0,
        cruise_force=2.0,
        grid_min_boids=0 if grid else 10**6,
    )
    flock.add(
        [
            FishBoid(
                Vector(random.uniform(0, WIDTH), random.uniform(0, HEIGHT)), 7
            )
            for _ in range(n)
        ]
    )
    return flock


def time_flocks(flocks):
    """
    Average ms per frame of steering and of the whole update, over FRAMES frames.
    """
    steer_ns = [0]
    for flock in flocks:
        flock.render = lambda: None
        # Instance attribute, so update() calls the timed wrapper
        flock._steer = timed(flock._steer, steer_ns)
    for _ in range(WARMUP):
        for flock in flocks:
            flock.update(DT)
    steer_ns[0] = 0
    t0 = time.monotonic_ns()
    for _ in range(FRAMES):
        for flock in flocks:
            flock.update(DT)
    total_ns = time.monotonic_ns() - t0
    return steer_ns[0] / FRAMES / 1e6, total_ns / FRAMES / 1e6


def timed(steer, acc):
    def wrapper(dt):
        t = time.monotonic_ns()
        steer(dt)
        acc[0] += time.monotonic_ns() - t

    return wrapper


def row(label, make):
    random.seed(1)
    steer, total = time_flocks(make())
    print("%-28s steer %7.2f ms | total %7.2f ms" % (label, steer, total))


def run(sizes=(4, 8, 16, 24, 32)):
    canvas = dio.Bitmap(WIDTH, HEIGHT, 16)
    print("-- koi flock (perception 10, fov 90)")
    for n in sizes:
        for grid in (False, True):
            row(
                "koi n=%-3d %s" % (n, "grid" if grid else "direct"),
                lambda: [koi_flock(canvas, n, grid)],
            )
    print("-- koi flock, steering every boid every frame")
    for n in sizes:
        for grid in (False, True):
            row(
                "koi n=%-3d %s all" % (n, "grid" if grid else "direct"),
                lambda: [koi_flock(canvas, n, grid, steer_half=False)],
            )
    print("-- background boids (perception 5, fov 270)")
    for grid in (False, True):
        row(
            "boids 3x10 %s" % ("grid" if grid else "direct"),
            lambda: [boid_flock(canvas, 10, grid) for _ in range(3)],
        )
    for grid in (False, True):
        row(
            "boids 1x50 %s" % ("grid" if grid else "direct"),
            lambda: [boid_flock(canvas, 50, grid)],
        )


if __name__ == "__main__":
    run()
