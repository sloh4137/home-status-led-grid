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
from graphics.graphics_helpers import dim_palette, make_canvas

import bitmaptools
import random

# Relative to this file, not the cwd (no os.path on CircuitPython)
POND_SPRITE = __file__.rsplit("/", 1)[0] + "/../sprites/pond_water.bmp"
POND_FPS = 8
POND_BRIGHTNESS = 0.1  # 0.0-1.0, applied to the pond sprite's palette

# Everything draws into one canvas sharing the pond sprite's palette, so displayio
# composites a single layer. The sprite only uses indices 0-5 of its 16, so creature
# colors go in the free indices after them.
KOI_COLOR = 6
BOID_COLOR = 7


def draw_frame(canvas, sprite, x, y):
    """
    Copy the canvas-sized region of sprite at (x, y) over the whole canvas.
    Module level so hardware/code.py can wrap it for render timing.
    """
    bitmaptools.blit(
        canvas, sprite, 0, 0, x1=x, y1=y, x2=x + canvas.width, y2=y + canvas.height
    )


def load_pond_water(width, height):
    """
    Load the animated pond water. The sprite is a horizontal strip of
    width x height frames. Returns (palette, update(dt), draw(canvas)): update
    advances the animation at POND_FPS regardless of the main loop's frame
    rate, and draw copies the current frame over the canvas, which also erases
    last frame's creatures.
    """
    bitmap, palette = load_image(POND_SPRITE)
    dim_palette(palette, POND_BRIGHTNESS)
    frames_per_row = bitmap.width // width
    num_frames = frames_per_row * (bitmap.height // height)

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

    def draw(canvas):
        frame = state[1]
        draw_frame(
            canvas,
            bitmap,
            (frame % frames_per_row) * width,
            (frame // frames_per_row) * height,
        )

    return palette, update, draw


def create_scene(width=64, height=64):
    """
    Build the scene. Returns (group, update(dt)) for the main loop.
    """

    group = dio.Group()
    palette, update_pond, draw_pond = load_pond_water(width, height)
    palette[KOI_COLOR] = Fish.COLOR
    palette[BOID_COLOR] = FishBoid.COLOR
    canvas = make_canvas(group, width, height, palette)

    # Koi Fish Flock
    koi_fish = [
        Fish(Vector(32, 32), 0.25, KOI_COLOR),
        Fish(Vector(16, 16), 0.15, KOI_COLOR),
        Fish(Vector(40, 40), 0.20, KOI_COLOR),
    ]
    koi_flock = FlockingBehavior(
        canvas,
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

    # Boids Flocks
    boid_creatures = []
    for _ in range(50):
        boid_creatures.append(
            FishBoid(
                Vector(random.randrange(0, width), random.randrange(0, height)),
                BOID_COLOR,
            )
        )

    flock_behavior = FlockingBehavior(
        canvas,
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

    def update(dt):
        # The background goes first: it erases last frame's creatures, then each
        # behavior draws its creatures on top
        update_pond(dt)
        draw_pond(canvas)
        koi_flock.update(dt)
        flock_behavior.update(dt)

    return group, update
