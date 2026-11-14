"""Visitors: creatures Home Assistant calls into the pond.

Each visitor has a condition on the sensor values (the washer's or the 3D
printer's plug drawing more than its on threshold). It arrives as soon as the
condition is true, but leaves only after the condition has been false for its
off delay, which rides over a washer's soaks and pauses and a printer's heater
cycling. The timer runs on the scene's real dt, not on poll times, so it keeps
counting while HA is quiet; unavailable counts as false, so a dead sensor
makes the visitor leave after the delay instead of staying forever.

Arriving, a visitor is built just outside a random edge, heading in, and the
walls bring it in on its own. Leaving, its walls go off (SwimBehavior.walls)
so it wanders out, and it's removed once it's fully off screen, or after
LEAVE_TIMEOUT seconds wherever it is (one pop, rare enough to accept). If
the condition comes back while it's leaving, its walls go back on and it
stays.

Each visitor has its own behavior with its one creature, built on arrival and
dropped on removal, so an absent visitor costs nothing per frame. Visitors
are never persisted, never age and never breed, and their species aren't in
SPECIES_BY_NAME: after a restart a running washer brings its visitor back on
the first poll.
"""

import random

from config import printer_on_watts, washer_on_watts
from creatures.colors import ELECTRIC, desaturate
from creatures.species import ELECTRIC_EEL
from creatures.spine_creature import SpineCreature
from graphics.vector import Vector

WASHER_OFF_SECONDS = 60
PRINTER_OFF_SECONDS = 60
# A leaving visitor still on screen after this long is removed anyway
LEAVE_TIMEOUT = 20

# Visitor states
AWAY = 0
PRESENT = 1  # condition true, or false for less than the off delay
LEAVING = 2  # walls off, wandering out

# The eel's ELECTRIC spots flicker through these (0xRRGGBB), a new pick every
# 2-3 frames, with now and then a full-white flash
EEL_SIZE = 100
EEL_FLICKER = (
    0x80F0FF,  # cyan-white
    0x80F0FF,
    0xC0FFFF,
    0xF0F070,  # pale yellow
    0x3050C0,  # dim blue
    0x2038A0,
)
EEL_FLASH = 0xFFFFFF
EEL_FLASH_CHANCE = 0.05


def watts(entry):
    """The entry's state as a float, or None if missing or not a number
    ("unavailable", "unknown")."""
    if entry is None:
        return None
    try:
        return float(entry[0])
    except (TypeError, ValueError):
        return None


def above(entry, on_watts):
    """True when watts(entry) is above on_watts. No number -> False."""
    w = watts(entry)
    return w is not None and w > on_watts


def power_above(key, on_watts):
    """A condition(values): the ``key`` entry draws more than on_watts."""

    def condition(values):
        return above(values.get(key), on_watts)

    return condition


def entry(width, height, inset):
    """
    (x, y, dx, dy): a spot inset px outside a random edge of the screen and a
    unit heading from it towards a random point in the middle half.
    """
    edge = random.randrange(4)
    if edge == 0:
        x, y = -inset, random.uniform(0, height)
    elif edge == 1:
        x, y = width + inset, random.uniform(0, height)
    elif edge == 2:
        x, y = random.uniform(0, width), -inset
    else:
        x, y = random.uniform(0, width), height + inset
    tx = random.uniform(width / 4, width * 3 / 4)
    ty = random.uniform(height / 4, height * 3 / 4)
    dx = tx - x
    dy = ty - y
    d = (dx * dx + dy * dy) ** 0.5
    return x, y, dx / d, dy / d


class Flicker:
    """
    Writes a palette slot from a table of colors every 2-3 frames, through
    desaturate() at the pond's current saturation step (PondColors), so the
    flicker goes gray with everything else.
    """

    def __init__(self, colors, slot, table, flash, flash_chance):
        self.colors = colors
        self.slot = slot
        self.table = table
        self.flash = flash
        self.flash_chance = flash_chance
        self._wait = 0

    def update(self):
        self._wait -= 1
        if self._wait > 0:
            return
        rand = random.random
        self._wait = 2 if rand() < 0.5 else 3
        if rand() < self.flash_chance:
            rgb = self.flash
        else:
            rgb = self.table[random.randrange(len(self.table))]
        self.colors.palette[self.slot] = desaturate(rgb, self.colors.step)


def build_eel(canvas, width, height):
    """The electric eel's behavior, with the eel just outside an edge, its
    body trailing straight out behind it, swimming in."""
    behavior = ELECTRIC_EEL.motion.build(canvas, width, height)
    x, y, dx, dy = entry(width, height, behavior.outside_window_size // 2)
    eel = SpineCreature(
        ELECTRIC_EEL,
        Vector(x, y),
        EEL_SIZE,
        ELECTRIC_EEL.varieties[0],
        random.randrange(0x10000),
    )
    # The spine starts trailing down from the head; lay it out behind the
    # heading instead, so at the top edge it doesn't hang onto the screen
    link = eel.link_size
    for i in range(len(eel.jx)):
        eel.jx[i] = x - dx * link * i
        eel.jy[i] = y - dy * link * i
        eel.ux[i] = dx
        eel.uy[i] = dy
    behavior.add([eel])
    behavior.vxs[0] = dx * behavior.cruise_speed
    behavior.vys[0] = dy * behavior.cruise_speed
    return behavior


class Visitor:
    """
    name, condition(values) -> bool, off_seconds, build(canvas, width,
    height) -> a behavior holding the one creature, and animate() (or None),
    called every frame while it's here (the eel's flicker).
    """

    def __init__(self, name, condition, off_seconds, build, animate=None):
        self.name = name
        self.condition = condition
        self.off_seconds = off_seconds
        self.build = build
        self.animate = animate
        self.state = AWAY
        self.behavior = None
        self._wanted = False  # the condition at the last set_sensors
        self._off_for = 0.0  # seconds the condition has been false while present
        self._leaving_for = 0.0  # seconds since it started leaving


class Visitors:
    """
    All visitors: ``set_sensors(values)`` on every sensor change,
    ``tick_timers(dt)`` every frame on the real dt (and while the display
    sleeps), ``update(motion_dt)`` every frame to swim and draw them, in the
    table's order.
    """

    def __init__(self, visitors, canvas, width, height):
        self.visitors = visitors
        self.canvas = canvas
        self.width = width
        self.height = height

    def set_sensors(self, values):
        for v in self.visitors:
            wanted = v.condition(values)
            v._wanted = wanted
            if not wanted:
                continue
            v._off_for = 0.0
            if v.state == AWAY:
                if v.build:
                    v.behavior = v.build(self.canvas, self.width, self.height)
                v.state = PRESENT
                print("visitor: %s arrive" % v.name)
            elif v.state == LEAVING:
                v.behavior.walls = True
                v.state = PRESENT
                print("visitor: %s stays" % v.name)

    def tick_timers(self, dt):
        for v in self.visitors:
            if v.state == PRESENT and not v._wanted:
                v._off_for += dt
                if v._off_for >= v.off_seconds:
                    v._off_for = 0.0
                    print("visitor: %s leave" % v.name)
                    if v.behavior is None:  # nothing to swim out
                        v.state = AWAY
                        continue
                    v._leaving_for = 0.0
                    v.behavior.walls = False
                    v.state = LEAVING
            elif v.state == LEAVING:
                v._leaving_for += dt
                if v._leaving_for >= LEAVE_TIMEOUT:
                    self._remove(v, "timeout")

    def update(self, motion_dt):
        for v in self.visitors:
            b = v.behavior
            if b is None:
                continue
            if v.animate:
                v.animate()
            b.update(motion_dt)
            if v.state == LEAVING:
                # Fully off screen: the head is past render_margin, which
                # covers the whole body
                m = b.render_margin
                x = b.xs[0]
                y = b.ys[0]
                if not (-m < x < b.width + m and -m < y < b.height + m):
                    self._remove(v, "gone")

    def _remove(self, v, why):
        v.state = AWAY
        v.behavior = None
        print("visitor: %s %s" % (v.name, why))


def visitors_from(config, colors):
    """The pond's visitors, with thresholds from settings.toml
    (config.Settings) and colors the scene's PondColors, for the flicker."""
    return (
        Visitor(
            "eel",
            power_above("washer_power", washer_on_watts(config)),
            WASHER_OFF_SECONDS,
            build_eel,
            Flicker(colors, ELECTRIC, EEL_FLICKER, EEL_FLASH, EEL_FLASH_CHANCE).update,
        ),
        # M5 builds the lily pad; until then the printer only prints
        Visitor(
            "lily",
            power_above("printer_power", printer_on_watts(config)),
            PRINTER_OFF_SECONDS,
            None,
        ),
    )
