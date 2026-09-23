from dataclasses import dataclass
from typing import Tuple, List
import math
import random

from behaviors.behavior import Behavior
from creatures.creature import Creature
from graphics.vector import Vector

DIRECTIONS = (-1, 0, 1)


class FlockingBehavior(Behavior):
    def __init__(
        self,
        width: int,
        height: int,
        outside_window_size: int,
        perception_radius: int,
        fov_degrees: int,
        separation_force: float,
        alignment_force: float,
        cohesion_force: float,
        avoidance_force: float,
        min_speed: float,
        max_speed: float,
    ):
        """
        Initialize a spatial hash since we're limited to a grid
        """
        self.width = width
        self.height = height
        self.outside_window_size = outside_window_size
        self.perception_radius = perception_radius
        self.fov_degrees = fov_degrees
        self.cos_half_sq = math.cos(math.radians(fov_degrees / 2)) ** 2

        self.separation_force = separation_force
        self.alignment_force = alignment_force
        self.cohesion_force = cohesion_force
        self.avoidance_force = avoidance_force
        self.min_speed = min_speed
        self.max_speed = max_speed

        self.grid: dict[Tuple[int, int], List[Creature]] = {}
        self.boids: List[Creature] = []
        # Velocity of each boid in pixels per second. This carries momentum between
        # frames, unlike Creature.velocity which is only the last frame's movement.
        self.velocities: dict[Creature, Vector] = {}

    def add_boids(self, boids: List[Creature]):
        self.boids.extend(boids)
        for boid in boids:
            # Start each boid moving in a random direction
            self.velocities[boid] = Vector.from_angle(
                random.uniform(0, math.tau),
                random.uniform(self.min_speed, self.max_speed),
            )

    def cell_coords(self, boid: Creature) -> Tuple[int, int]:
        x, y = int(boid.x // self.perception_radius), int(
            boid.y // self.perception_radius
        )
        return (x, y)

    def in_fov(
        self, boid_position: Vector, boid_direction: Vector, other: Creature
    ) -> bool:
        if self.fov_degrees >= 360:
            return True

        to_other = other.position() - boid_position
        dist_squared = to_other.x**2 + to_other.y**2
        # A negative dot product means we're behind the boid
        dot_product = to_other.x * boid_direction.x + to_other.y * boid_direction.y

        if self.fov_degrees <= 180:
            # Narrow hemisphere in front of boid so ignore everything behind.
            if dot_product <= 0:
                return False

            return dot_product**2 >= dist_squared * self.cos_half_sq
        else:
            # Wider than 180, so we only remove a small cone behind.
            if dot_product >= 0:
                return True
            return dot_product**2 <= dist_squared * self.cos_half_sq

    def get_neighbors(self, boid: Creature) -> List[Creature]:
        """
        Get neighbors from the spatial grid.
        Account for view angle for the given boid and remove neighbors it can't see.

        For now we'll just return all of the neighbors as one. Maybe later we can
        support different radii for each value.
        """
        x, y = self.cell_coords(boid)
        neighbors = []
        for dx in DIRECTIONS:
            for dy in DIRECTIONS:
                cell = self.grid.get((x + dx, y + dy))
                if not cell:
                    continue

                # Account for the FOV to see if the other boids are in view

                boid_direction = self.velocities[boid].normalized()
                for other in cell:
                    # Ignore if it's the same object or not in FOV
                    if other is boid or not self.in_fov(
                        boid.position(), boid_direction, other
                    ):
                        continue

                    neighbors.append(other)

        return neighbors

    def separation(self, boid: Creature, neighbors: List[Creature]) -> Vector:
        """
        Move away from other boids.
        """
        if not neighbors:
            return Vector(0, 0)

        vec = Vector(0, 0)
        boid_position = boid.position()
        for n in neighbors:
            away = boid_position - n.position()
            dist = away.magnitude()
            # Weight by 1/distance so closer neighbors push harder
            vec += away / (dist * dist)

        return vec * self.separation_force

    def cohesion(self, boid: Creature, neighbors: List[Creature]) -> Vector:
        """
        Move towards the center of mass of other boids.
        """
        if not neighbors:
            return Vector(0, 0)

        average_vec = Vector(0, 0)
        for n in neighbors:
            average_vec += n.position()

        move_towards_average = (average_vec / len(neighbors)) - boid.position()
        return move_towards_average * self.cohesion_force

    def alignment(self, boid: Creature, neighbors: List[Creature]) -> Vector:
        """
        Match the speed and direction of other boids
        """
        if not neighbors:
            return Vector(0, 0)

        average_vec = Vector(0, 0)
        for n in neighbors:
            average_vec += self.velocities[n]

        match_average = (average_vec / len(neighbors)) - self.velocities[boid]
        return match_average * self.alignment_force

    def avoidance(self, boid: Creature) -> Vector:
        """
        Move boids away from obstacles such as the walls.
        """
        dx, dy = 0.0, 0.0
        if boid.x <= -self.outside_window_size:
            dx += self.avoidance_force

        if boid.x >= self.width + self.outside_window_size:
            dx -= self.avoidance_force

        if boid.y <= -self.outside_window_size:
            dy += self.avoidance_force

        if boid.y >= self.height + self.outside_window_size:
            dy -= self.avoidance_force

        return Vector(dx, dy)

    def update(self, dt: float):
        """
        1. Clear previous grid and add all boids to grid
        2. For each boid, get neighbors (maybe separate radius for separation, alignment)
        3. Add separation
        4. Add alignment
        5. Add cohesion
        6. Add avoidance
        7. Add noise
        8. Apply the summed forces as acceleration and clamp speed to [min_speed, max_speed]
        9. Move boid based on velocity
        """

        # 1. Clear grid and add all boids
        self.grid.clear()
        for boid in self.boids:
            coords = self.cell_coords(boid)
            self.grid.setdefault(coords, []).append(boid)

        # Now that grid is computed, we can proceed with steps #2-8. Compute every new
        # velocity before moving anything so each boid sees the same snapshot.
        new_velocities: dict[Creature, Vector] = {}
        for boid in self.boids:
            # 2. Get neighbors
            neighbors = self.get_neighbors(boid)

            # 3, 4, 5, 6: Separation, alignment, cohesion, avoidance
            move_vec = Vector(0, 0)
            move_vec += self.separation(boid, neighbors)
            move_vec += self.alignment(boid, neighbors)
            move_vec += self.cohesion(boid, neighbors)
            move_vec += self.avoidance(boid)

            # 7: Add random noise
            move_vec += Vector(random.uniform(-1, 1), random.uniform(-1, 1))

            # 8. Apply forces as acceleration and clamp speed to [min_speed, max_speed]
            velocity = self.velocities[boid] + move_vec * dt
            speed = max(self.min_speed, min(velocity.magnitude(), self.max_speed))
            new_velocities[boid] = velocity.with_mag(speed)

        # 9. Move boids
        for boid in self.boids:
            self.velocities[boid] = new_velocities[boid]
            boid.move(new_velocities[boid] * dt)
            boid.render()
