"""
Scene with procedural generated fish
"""

from _dio import dio
from config import Settings, pond_time_scale, zap_max_watts, zap_min_watts
from creatures import colors
from creatures.colors import MAX_LEVEL, PondColors, co2_level
from creatures.fish_boid import FishBoid
from creatures.species import KOI, KOI_WANDER as KOI_WANDER_MOTION
from graphics.vector import Vector
from behaviors.flocking import FlockingBehavior
from behaviors.lifecycle import Pond
from _imageload import load_image
from graphics.graphics_helpers import dim_palette, make_canvas
from scenes.effects import zap_rate
from scenes.visitors import Visitors, visitors_from, watts

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

# CO2 -> speed: every moving thing runs on dt * speed, from 1.0 in clean air
# down to MIN_SPEED at MAX_LEVEL, in tenths. The lifecycle clock and the water
# animation stay on the real dt.
MIN_SPEED = 0.4
# How fast speed eases toward its target, per second, so a 0.1 step in the
# target takes a few seconds instead of showing as a sudden slowdown
SPEED_EASE = 0.5


def speed_for_level(level):
    """1.0 at level 0, down to MIN_SPEED at MAX_LEVEL, in whole tenths."""
    span = 10 - int(MIN_SPEED * 10 + 0.5)
    return (10 - (level * span + MAX_LEVEL // 2) // MAX_LEVEL) / 10


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


def create_scene(width=64, height=64, store=None, config=None):
    """
    Build the scene. Returns (group, update(dt), set_sensors(values)) for the
    main loop. set_sensors gets the whole sensor values dict whenever it
    changes; the CO2 level drains the color out of the pond (creatures and
    water) and slows every moving thing (speed_for_level), easing in over a
    few seconds. The washer's and printer's plug power call in visitors
    (scenes/visitors.py) and the house's total power sets the zap rate
    (scenes/effects.py); for now neither draws anything.

    The fish come from the store's ``pond`` section (behaviors/lifecycle.py),
    or a fresh pond without one; the store then saves the pond with the rest
    of the document. A fresh or repaired pond marks the store dirty, so the
    fixed version is what gets saved, and so does every change the lifecycle
    makes (aging, births, deaths). config (settings.toml) gives
    POND_TIME_SCALE, the plugs' on watts and the zap power range.
    """

    group = dio.Group()
    palette, update_pond, draw_pond = load_pond_water(width, height)
    pond_colors = PondColors(palette)
    canvas = make_canvas(group, width, height, palette)

    # The fish, one behavior per species present, so species never flock
    # together
    pond = Pond.from_dict(
        store.section("pond") if store else None,
        canvas,
        width,
        height,
        {KOI: KOI_WANDER_MOTION} if KOI_WANDER else None,
        time_scale=pond_time_scale(config) if config else 1,
        on_change=store.mark_dirty if store else None,
    )
    if pond.time_scale != 1:
        print("pond: time x%d" % pond.time_scale)
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

    # [current speed, target speed]
    speed = [1.0, 1.0]

    # HA effects. M3: the visitor conditions (printed) and the zap rate
    settings = config or Settings({})
    visitors = Visitors(visitors_from(settings))
    zap_lo, zap_hi = zap_min_watts(settings), zap_max_watts(settings)
    # [total power W last seen (to skip unchanged reads), zaps per second]
    zaps = [None, 0.0]

    def set_sensors(values):
        level = co2_level(values)
        pond_colors.set_step(colors.saturation_step(level))
        target = speed_for_level(level)
        if target != speed[1]:
            speed[1] = target
            print("pond: speed -> %.1f" % target)
        visitors.set_sensors(values)
        w = watts(values.get("total_power"))
        if w != zaps[0]:
            zaps[0] = w
            zaps[1] = zap_rate(w, zap_lo, zap_hi)

    def update(dt):
        current, target = speed
        if current != target:
            current += (target - current) * min(1.0, dt * SPEED_EASE)
            # Snap the last sliver so the ease ends
            if abs(target - current) < 0.005:
                current = target
            speed[0] = current
        motion_dt = dt * current
        visitors.tick_timers(dt)  # real time, like the lifecycle
        # The background goes first: it erases last frame's creatures, then each
        # behavior draws its creatures on top
        update_pond(dt)
        draw_pond(canvas)
        pond.update(dt, motion_dt)
        for flock in boid_flocks:
            flock.update(motion_dt)

    return group, update, set_sensors
