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
from _imageload import load_image
from graphics.graphics_helpers import dim_palette

import random

# Relative to this file, not the cwd (no os.path on CircuitPython)
POND_SPRITE = __file__.rsplit("/", 1)[0] + "/../sprites/pond_water.bmp"
POND_FPS = 8
POND_BRIGHTNESS = 0.1  # 0.0-1.0, applied to the pond sprite's palette


def add_pond_water(group, width, height):
    """
    Append the animated pond water to group. The sprite is a horizontal strip
    of width x height frames. Returns update(dt), which advances the animation
    at POND_FPS regardless of the main loop's frame rate.
    """
    bitmap, palette = load_image(POND_SPRITE)
    dim_palette(palette, POND_BRIGHTNESS)
    num_frames = (bitmap.width // width) * (bitmap.height // height)
    grid = dio.TileGrid(
        bitmap, pixel_shader=palette, tile_width=width, tile_height=height
    )
    group.append(grid)

    frame_time = 1 / POND_FPS
    state = [0.0, 0]  # [time since last frame change, current frame]

    def update(dt):
        state[0] += dt
        if state[0] < frame_time:
            return
        # Skip ahead if a slow main-loop frame spanned more than one pond frame
        steps = int(state[0] / frame_time)
        state[0] -= steps * frame_time
        state[1] = (state[1] + steps) % num_frames
        grid[0] = state[1]

    return update


def create_scene(width=64, height=64):
    """
    Build the scene. Returns (group, update(dt)) for the main loop.
    """

    group = dio.Group()
    update_pond = add_pond_water(group, width, height)

    # Koi Fish Flock
    koi_fish = [
        Fish(Vector(32, 32), 0.25),
        Fish(Vector(16, 16), 0.15),
        Fish(Vector(40, 40), 0.20),
    ]
    koi_flock = FlockingBehavior(
        width,
        height,
        outside_window_size=10,
        wall_avoid_distance=20,
        perception_radius=5,
        fov_degrees=90,
        separation_force=100.0,
        alignment_force=1.0,
        cohesion_force=1.0,
        avoidance_force=200.0,
        min_speed=1.0,
        max_speed=25.0,
        cruise_speed=20.0,
        cruise_force=2.0,
    )
    koi_flock.add_boids(koi_fish)
    # circle_behavior = CircleBehavior(Vector(20, 20), 20, 100)
    # circle_behavior.add_creatures(creatures)

    # Boids Flocks
    boid_creatures = []
    for _ in range(50):
        boid_creatures.append(
            FishBoid(Vector(random.randrange(0, width), random.randrange(0, height)))
        )

    flock_behavior = FlockingBehavior(
        width,
        height,
        outside_window_size=15,
        wall_avoid_distance=20,
        perception_radius=5,
        fov_degrees=270,
        separation_force=75.0,
        alignment_force=5.0,
        cohesion_force=2,
        avoidance_force=200.0,
        min_speed=1.0,
        max_speed=50.0,
        cruise_speed=40.0,
        cruise_force=2.0,
    )
    flock_behavior.add_boids(boid_creatures)

    for c in koi_fish:
        group.append(c.grid)

    for b in boid_creatures:
        group.append(b.grid)

    def update(dt):
        koi_flock.update(dt)
        flock_behavior.update(dt)
        update_pond(dt)

    return group, update
