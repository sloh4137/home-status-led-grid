"""
Scene with procedural generated fish
"""

from _dio import dio
from creatures import colors
from creatures.colors import CreatureColors
from creatures.fish_boid import FishBoid
from creatures.species import KOI, KOI_WANDER as KOI_WANDER_MOTION
from graphics.vector import Vector
from behaviors.flocking import FlockingBehavior
from behaviors.lifecycle import Pond
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
# colors go in the free indices after them (creatures/colors.py).
BOID_COLOR = colors.BOID

# Background boids: independent flocks of BOIDS_PER_FLOCK, each small enough for
# the direct neighbour loop (under grid_min_boids)
BOID_FLOCKS = 3
BOIDS_PER_FLOCK = 10

# Try the koi on WanderBehavior instead of flocking
KOI_WANDER = False


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


def create_scene(width=64, height=64, store=None):
    """
    Build the scene. Returns (group, update(dt), set_sensors(values)) for the
    main loop. set_sensors gets the whole sensor values dict whenever it
    changes; the CO2 level dims the creatures (not the water).

    The fish come from the store's ``pond`` section (behaviors/lifecycle.py),
    or a fresh pond without one; the store then saves the pond with the rest
    of the document. A fresh or repaired pond marks the store dirty, so the
    fixed version is what gets saved.
    """

    group = dio.Group()
    palette, update_pond, draw_pond = load_pond_water(width, height)
    creature_colors = CreatureColors(palette)
    canvas = make_canvas(group, width, height, palette)

    # The fish, one behavior per species present, so species never flock
    # together
    pond = Pond.from_dict(
        store.section("pond") if store else None,
        canvas,
        width,
        height,
        {KOI: KOI_WANDER_MOTION} if KOI_WANDER else None,
    )
    if store:
        store.provide("pond", pond.to_dict)
        if pond.changed:
            store.mark_dirty()

    # Background boid flocks, each starting in its own third of the tank. They
    # don't see each other, so they pass through one another as separate schools.
    boid_flocks = []
    third = width / BOID_FLOCKS
    for k in range(BOID_FLOCKS):
        flock = FlockingBehavior(
            canvas,
            width,
            height,
            outside_window_size=30,
            wall_avoid_distance=30,
            perception_radius=10,
            fov_degrees=270,
            separation_force=25.0,
            alignment_force=5.0,
            cohesion_force=10.0,
            avoidance_force=200.0,
            random_steer=1,
            min_speed=1.0,
            max_speed=50.0,
            cruise_speed=40.0,
            cruise_force=2.0,
        )
        flock.add(
            [
                FishBoid(
                    Vector(
                        random.uniform(k * third, (k + 1) * third),
                        random.randrange(0, height),
                    ),
                    BOID_COLOR,
                )
                for _ in range(BOIDS_PER_FLOCK)
            ]
        )
        boid_flocks.append(flock)

    def update(dt):
        # The background goes first: it erases last frame's creatures, then each
        # behavior draws its creatures on top
        update_pond(dt)
        draw_pond(canvas)
        pond.update(dt)
        for flock in boid_flocks:
            flock.update(dt)

    return group, update, creature_colors.set_sensors
