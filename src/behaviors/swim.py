import math
import random

from behaviors.behavior import Behavior
from creatures.creature import Creature


class SwimBehavior(Behavior):
    """
    Base for behaviors that swim creatures around a walled tank: flat per-creature
    state, the soft wall push, integration, set_state and on-screen render
    culling. Subclasses write only _steer(dt), which updates the velocities of
    every creature it steers in one loop.

    Method calls and allocations are what cost in CircuitPython, so there is one
    update() per frame for the whole behavior, and no method call per creature
    per frame except Creature.set_state and Creature.render.
    """

    def __init__(
        self,
        bitmap,
        width: int,
        height: int,
        outside_window_size: int,
        wall_avoid_distance: int,
        avoidance_force: float,
        min_speed: float,
        max_speed: float,
        cruise_speed: float,
    ):
        """
        The creatures render into bitmap, the scene's full-screen canvas, which the
        scene redraws the background into before each update.
        """
        self.bitmap = bitmap
        self.width = width
        self.height = height
        self.outside_window_size = outside_window_size
        self.wall_avoid_distance = wall_avoid_distance
        self.avoidance_force = avoidance_force
        self.min_speed = min_speed
        self.max_speed = max_speed
        self.cruise_speed = cruise_speed

        # Actual size of the area the creatures swim around in. The walls sit
        # outside_window_size beyond each edge of the window, so a positive value
        # lets creatures swim off screen before turning back.
        self.left = -outside_window_size
        self.right = width + outside_window_size
        self.top = -outside_window_size
        self.bottom = height + outside_window_size

        # Inner rectangle where every wall is at least wall_avoid_distance away, so
        # avoidance is zero and can be skipped. Clamped at 0 because ease_in still
        # pushes creatures that are past the wall when wall_avoid_distance <= 0.
        avoid = max(wall_avoid_distance, 0)
        self.safe_left = self.left + avoid
        self.safe_right = self.right - avoid
        self.safe_top = self.top + avoid
        self.safe_bottom = self.bottom - avoid

        self.creatures: list[Creature] = []
        # Flat per-creature state indexed by position in self.creatures, so the hot
        # loops read plain floats instead of chasing Creature/Vector attributes.
        # These positions are the source of truth: the behavior integrates them each
        # frame and pushes them to the creatures with Creature.set_state, rather
        # than reading positions back from them.
        self.xs: list[float] = []
        self.ys: list[float] = []
        # Velocity in pixels per second. This carries momentum between frames,
        # unlike Creature.velocity which is only the last frame's movement.
        self.vxs: list[float] = []
        self.vys: list[float] = []
        # How far past the window edge a creature can be and still draw a pixel on
        # screen. +1 covers flooring the position to a pixel.
        self.render_margin = 1

    # ------------------------------------------------------------ membership

    def add(self, creatures: list[Creature]):
        """
        Add creatures at their current positions, each moving in a random
        direction at cruise speed.
        """
        for creature in creatures:
            self.creatures.append(creature)
            self.xs.append(creature.x)
            self.ys.append(creature.y)
            self.render_margin = max(self.render_margin, creature.render_radius + 1)
            angle = random.uniform(0, 2 * math.pi)
            self.vxs.append(math.cos(angle) * self.cruise_speed)
            self.vys.append(math.sin(angle) * self.cruise_speed)
            self._add_state()

    def _add_state(self):
        """
        Append subclass per-creature state for a creature just added. Lists
        appended here must also be returned by _state_lists.
        """

    def _state_lists(self) -> list:
        """
        Every per-creature list, so remove() keeps them all aligned. Read the
        attributes each call, since update() may replace a list with a new one.
        """
        return [self.creatures, self.xs, self.ys, self.vxs, self.vys]

    def remove(self, creature: Creature):
        """
        Remove a creature with a swap-remove: the last creature moves into its
        slot, so every list stays dense. Indices into the lists are only valid
        until the next add or remove.
        """
        i = self.creatures.index(creature)
        last = len(self.creatures) - 1
        for values in self._state_lists():
            values[i] = values[last]
            values.pop()

    def __len__(self):
        return len(self.creatures)

    # ------------------------------------------------------------ walls

    def ease_in(self, distance_to_wall: float) -> float:
        """
        Ease the avoidance force in as a creature approaches a wall.
        Returns 0 when wall_avoid_distance or further away from the wall, ramping
        up to 1 at the wall and staying at 1 past it.
        """
        if self.wall_avoid_distance <= 0:
            return 1.0 if distance_to_wall <= 0 else 0.0

        # How far into the avoid distance are we?
        # Aka in a normal animation, how far along are we from 0 to 1
        time = 1.0 - distance_to_wall / self.wall_avoid_distance
        time = max(0.0, min(time, 1.0))
        return time**2

    def avoidance(self, x: float, y: float) -> tuple[float, float]:
        """
        Push creatures away from the walls, more as they get within
        wall_avoid_distance of one. Only call it outside the safe rectangle;
        inside it the result is always zero.
        """
        dx = self.ease_in(x - self.left) - self.ease_in(self.right - x)
        dy = self.ease_in(y - self.top) - self.ease_in(self.bottom - y)

        return dx * self.avoidance_force, dy * self.avoidance_force

    # ------------------------------------------------------------ frame

    def _steer(self, dt: float):
        """
        Update self.vxs / self.vys for the creatures steered this frame, clamped
        to [min_speed, max_speed]. Either change the lists in place or replace
        them with new ones; update() reads them afterwards. Positions must not be
        changed here.
        """
        raise NotImplementedError

    def update(self, dt: float):
        """
        Steer, move every creature by its velocity, push the new state to the
        creatures, then render the ones on screen.
        """
        self._steer(dt)

        creatures = self.creatures
        xs = self.xs
        ys = self.ys
        vxs = self.vxs
        vys = self.vys
        for i in range(len(creatures)):
            vx = vxs[i]
            vy = vys[i]
            x = xs[i] + vx * dt
            y = ys[i] + vy * dt
            xs[i] = x
            ys[i] = y
            creatures[i].set_state(x, y, vx, vy)

        self.render()

    def render(self):
        """
        Draw every creature that can reach the screen. Off-screen creatures are
        skipped; the scene's background redraw erases wherever they were last
        drawn.
        """
        bitmap = self.bitmap
        creatures = self.creatures
        xs = self.xs
        ys = self.ys
        margin = self.render_margin
        view_left = -margin
        view_right = self.width + margin
        view_top = -margin
        view_bottom = self.height + margin
        for i in range(len(creatures)):
            x = xs[i]
            y = ys[i]
            if view_left < x < view_right and view_top < y < view_bottom:
                creatures[i].render(bitmap)
