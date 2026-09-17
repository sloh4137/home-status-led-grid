from behaviors.behavior import Behavior
from graphics.vector import Vector
from creatures.creature import Creature
from typing import List
import math


class CircleBehavior(Behavior):

    def __init__(
        self, center: Vector, radius: float, linear_speed: float, epsilon: float = 0.1
    ):
        self.creatures = []
        self.center = center
        self.radius = radius
        self.linear_speed = linear_speed
        self.angular_speed = linear_speed / radius if radius > epsilon else 1.0
        self.epsilon = epsilon
        self.time = 0.0

    def get_position_on_circle(self, angle: float) -> Vector:
        return Vector(
            self.center.x + self.radius * math.cos(angle),
            self.center.y + self.radius * math.sin(angle),
        )

    def get_movement_delta_towards_circle(
        self,
        position: Vector,
        entry_angle: float,
        closest_point: Vector,
        dist_to_closest: float,
        dt: float,
    ) -> Vector:
        step_dist = self.linear_speed * dt

        # We won't reach on this frame so move towards closest point
        if dist_to_closest > step_dist:
            direction = (closest_point - position).normalized()
            return direction * step_dist

        # We will reach within this frame so after that use the leftover time to orbit
        time_to_reach = dist_to_closest / self.linear_speed
        remaining_time = dt - time_to_reach

        final_angle = entry_angle + self.angular_speed * remaining_time
        final_pos = self.get_position_on_circle(final_angle)
        return final_pos - position

    def get_movement_delta_on_circle(
        self, position: Vector, entry_angle: float, dt: float
    ) -> Vector:
        target_angle = entry_angle + self.angular_speed * dt
        next_pos = self.get_position_on_circle(target_angle)
        return next_pos - position

    def get_movement_delta(self, position: Vector, dt: float) -> Vector:
        """
        Move the position either towards the circle if it isn't on it or around the circle if it is.
        """
        if self.radius <= self.epsilon or self.linear_speed < self.epsilon:
            return Vector(0, 0)

        to_pos = position - self.center
        dist_to_center = to_pos.magnitude()

        # Find the closest point on the circle and current angle
        if dist_to_center < self.epsilon:
            # We're at the center so there's no "closest" point to move to since we're equidistance so choose
            # a point based on the time-based angle
            entry_angle = self.angular_speed * self.time
        else:
            entry_angle = to_pos.heading()

        closest_point = self.get_position_on_circle(entry_angle)
        dist_to_closest = (closest_point - position).magnitude()
        is_on_circle = dist_to_closest <= self.epsilon

        #
        if is_on_circle:
            return self.get_movement_delta_on_circle(position, entry_angle, dt)
        else:
            return self.get_movement_delta_towards_circle(
                position, entry_angle, closest_point, dist_to_closest, dt
            )

    def add_creatures(self, creatures: List[Creature]) -> None:
        self.creatures.extend(creatures)

    def update(self, dt: float):
        for c in self.creatures:
            c.move(self.get_movement_delta(c.position(), dt))
            c.render()

        self.time += dt
