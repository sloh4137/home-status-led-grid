import math
import random

from behaviors.swim import SwimBehavior


class WanderBehavior(SwimBehavior):
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
        max_turn: float,
        retarget: tuple = (1.0, 4.0),
        turn_ease: float = 2.0,
        speed_variation: float = 0.3,
        speed_ease: float = 1.0,
        pause_chance: float = 0.0,
        hug_distance: float = 0.0,
        hug_chance: float = 0.0,
        leave_chance: float = 0.0,
        hug_gain: float = 3.0,
    ):
        """
        Creatures that swim on their own along smooth, curving paths, with no
        neighbours at all, so the cost is a constant per creature.

        Each creature has a turn rate (rad/s, positive turns clockwise on screen).
        Every retarget seconds (a random draw in that range per creature, so they
        don't all change at once) it picks a new target turn in +-max_turn and a
        new cruise speed: cruise_speed +- speed_variation (a fraction), or a pause
        (min_speed) with probability pause_chance. Each frame the turn rate eases
        towards its target at turn_ease per second, and the speed towards its
        cruise speed at speed_ease per second.

        Near a wall (outside the safe rectangle) the target turn points the
        creature back towards the middle of the tank, and the wall push applies.
        Keep min_speed above 0, or a paused creature loses its heading.

        Edge hugging (the catfish), on when hug_distance > 0: a hugging creature
        swims along the nearest screen edge, hug_distance px in from it, and
        turns the corners: heading into an edge, it turns the way that leads
        towards the middle, so a corner never traps it. It may cut a corner
        slightly off screen. Its target turn steers towards the edge's tangent
        (whichever way it's already going) tilted in or out by how far it is
        from hug_distance, at up to hug_gain * max_turn for a big error,
        clamped to +-max_turn. The random target turn is kept as a small
        wobble on top. The screen edges are used, not the walls, which sit
        outside_window_size beyond them.

        At each retarget a roaming creature starts hugging with probability
        hug_chance and a hugging one leaves the edge with leave_chance, so it
        spends about hug_chance / (hug_chance + leave_chance) of its time on
        the edges and now and then crosses the pond.
        """
        super().__init__(
            bitmap,
            width,
            height,
            outside_window_size,
            wall_avoid_distance,
            avoidance_force,
            min_speed,
            max_speed,
            cruise_speed,
        )
        self.max_turn = max_turn
        self.retarget = retarget
        self.turn_ease = turn_ease
        self.speed_variation = speed_variation
        self.speed_ease = speed_ease
        self.pause_chance = pause_chance
        self.hug_distance = hug_distance
        self.hug_chance = hug_chance
        self.leave_chance = leave_chance
        self.hug_gain = hug_gain
        self.center_x = width / 2
        self.center_y = height / 2

        # Per-creature state, aligned with the base lists
        self.turns: list[float] = []  # current turn rate
        self.target_turns: list[float] = []
        self.cruises: list[float] = []  # current cruise speed
        self.timers: list[float] = []  # seconds until the next retarget
        self.hugging: list[bool] = []  # following an edge (hug_distance > 0)

    def _add_state(self):
        self.turns.append(0.0)
        self.target_turns.append(random.uniform(-self.max_turn, self.max_turn))
        self.cruises.append(self.cruise_speed)
        # Stagger the first retarget across the whole range
        self.timers.append(random.uniform(0, self.retarget[1]))
        # Start in the long-run split between hugging and roaming
        odds = self.hug_chance + self.leave_chance
        self.hugging.append(
            self.hug_distance > 0
            and odds > 0
            and random.random() < self.hug_chance / odds
        )

    def _state_lists(self) -> list:
        return super()._state_lists() + [
            self.turns,
            self.target_turns,
            self.cruises,
            self.timers,
            self.hugging,
        ]

    def _steer(self, dt: float):
        xs = self.xs
        ys = self.ys
        vxs = self.vxs
        vys = self.vys
        turns = self.turns
        target_turns = self.target_turns
        cruises = self.cruises
        timers = self.timers
        hugging = self.hugging

        max_turn = self.max_turn
        retarget_lo, retarget_hi = self.retarget
        pause_chance = self.pause_chance
        cruise_lo = self.cruise_speed * (1 - self.speed_variation)
        cruise_hi = self.cruise_speed * (1 + self.speed_variation)
        turn_k = min(1.0, self.turn_ease * dt)
        speed_k = min(1.0, self.speed_ease * dt)
        min_speed = self.min_speed
        max_speed = self.max_speed
        safe_left = self.safe_left
        safe_right = self.safe_right
        safe_top = self.safe_top
        safe_bottom = self.safe_bottom
        center_x = self.center_x
        center_y = self.center_y
        hug_distance = self.hug_distance
        hug_on = hug_distance > 0
        hug_chance = self.hug_chance
        leave_chance = self.leave_chance
        hug_gain = self.hug_gain
        # Screen edges, for hugging
        right = self.width
        bottom = self.height
        uniform = random.uniform
        rand = random.random
        sqrt = math.sqrt
        for i in range(len(self.creatures)):
            # Pick a new target turn and cruise speed every few seconds
            timer = timers[i] - dt
            if timer <= 0:
                timer += uniform(retarget_lo, retarget_hi)
                target_turns[i] = uniform(-max_turn, max_turn)
                if pause_chance and rand() < pause_chance:
                    cruises[i] = min_speed
                else:
                    cruises[i] = uniform(cruise_lo, cruise_hi)
                if hug_on:
                    if hugging[i]:
                        if rand() < leave_chance:
                            hugging[i] = False
                    elif rand() < hug_chance:
                        hugging[i] = True
            timers[i] = timer

            x = xs[i]
            y = ys[i]
            vx = vxs[i]
            vy = vys[i]
            target = target_turns[i]
            near_wall = not (safe_left < x < safe_right and safe_top < y < safe_bottom)
            if hug_on and hugging[i]:
                speed = sqrt(vx * vx + vy * vy)
                # The nearest screen edge: its distance d and inward normal
                # (nx, ny). The tangent is the normal turned a quarter,
                # flipped to the way the creature is already going.
                d = x
                nx = 1.0
                ny = 0.0
                if right - x < d:
                    d = right - x
                    nx = -1.0
                if y < d:
                    d = y
                    nx = 0.0
                    ny = 1.0
                if bottom - y < d:
                    d = bottom - y
                    nx = 0.0
                    ny = -1.0
                tx = -ny
                ty = nx
                along = vx * tx + vy * ty
                # Heading mostly into the edge (at a corner, or when it starts
                # hugging): which way is a near tie, so go the way that leads
                # away from the corner, towards the middle of the tank
                if -0.5 * speed < along < 0.5 * speed:
                    along = (center_x - x) * tx + (center_y - y) * ty
                if along < 0:
                    tx = -tx
                    ty = -ty
                # Tilt in when too far out, out when too close, up to 45 deg
                k = (hug_distance - d) / hug_distance
                k = -1.0 if k < -1.0 else 1.0 if k > 1.0 else k
                dx = tx + nx * k
                dy = ty + ny * k
                # Turn towards (dx, dy): the cross product's sign is the side,
                # its size (normalised) how far off the heading is. Anything
                # behind gets the full turn.
                norm = speed * sqrt(dx * dx + dy * dy)
                if norm > 1e-9:
                    cross = (vx * dy - vy * dx) / norm
                    if vx * dx + vy * dy < 0:
                        cross = 1.0 if cross >= 0 else -1.0
                    cross *= hug_gain
                    cross = -1.0 if cross < -1.0 else 1.0 if cross > 1.0 else cross
                    # The random target stays on as a small wobble
                    target = max_turn * cross + target * 0.25
                    if target > max_turn:
                        target = max_turn
                    elif target < -max_turn:
                        target = -max_turn
            elif near_wall:
                # Turn towards the middle: the sign of the cross product of the
                # heading and the offset to the middle says which way it is
                cross = vx * (center_y - y) - vy * (center_x - x)
                target = max_turn if cross > 0 else -max_turn

            # Ease the turn rate towards its target and rotate the heading by it.
            # The small-angle rotation grows the speed slightly; the clamp below
            # renormalises it.
            turn = turns[i]
            turn += (target - turn) * turn_k
            turns[i] = turn
            a = turn * dt
            vx, vy = vx - vy * a, vy + vx * a

            if near_wall:
                ax, ay = self.avoidance(x, y)
                vx += ax * dt
                vy += ay * dt

            # Ease the speed towards the cruise speed, clamped
            speed = sqrt(vx * vx + vy * vy)
            if speed != 0:
                new_speed = speed + (cruises[i] - speed) * speed_k
                scale = max(min_speed, min(new_speed, max_speed)) / speed
                vx *= scale
                vy *= scale
            vxs[i] = vx
            vys[i] = vy


class Wander:
    """
    Motion record for a species: the WanderBehavior settings as data. The
    species table holds one, and the pond builds one behavior per species.
    """

    def __init__(self, **settings):
        self.settings = settings

    def build(self, bitmap, width, height):
        return WanderBehavior(bitmap, width, height, **self.settings)
