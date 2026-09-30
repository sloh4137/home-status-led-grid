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
        wall_avoid_distance: int,
        perception_radius: int,
        fov_degrees: int,
        separation_force: float,
        alignment_force: float,
        cohesion_force: float,
        avoidance_force: float,
        min_speed: float,
        max_speed: float,
        cruise_speed: float,
        cruise_force: float,
    ):
        """
        Flocking behavior for a group of boids.
        """
        self.width = width
        self.height = height
        self.outside_window_size = outside_window_size
        self.wall_avoid_distance = wall_avoid_distance

        # Actual size of the grid that the boids will wander around.
        self.left = -outside_window_size
        self.right = width + outside_window_size
        self.top = -outside_window_size
        self.bottom = height + outside_window_size

        # How much the boids can see
        self.perception_radius = perception_radius
        self.fov_degrees = fov_degrees
        self.cos_half_sq = math.cos(math.radians(fov_degrees / 2)) ** 2

        # Forces that act on the boid
        self.separation_force = separation_force
        self.alignment_force = alignment_force
        self.cohesion_force = cohesion_force
        self.avoidance_force = avoidance_force
        self.min_speed = min_speed
        self.max_speed = max_speed
        # Speed boids drift back to after being slowed down or sped up by other
        # forces. cruise_force is how quickly (per second) they close the gap.
        self.cruise_speed = cruise_speed
        self.cruise_force = cruise_force

        # Spatial grid to find the neighbors of boids. The swim area has fixed bounds,
        # so it's a flat list of cells preallocated once. Boids aren't clamped to the
        # swim area, so allow one extra cell on each side for overshoot; boids further
        # out are clamped into it. One more cell of padding on each side keeps the 3x3
        # neighborhood lookups in range without bounds checks.
        self.min_cx = int(self.left // perception_radius) - 1
        self.max_cx = int(self.right // perception_radius) + 1
        self.min_cy = int(self.top // perception_radius) - 1
        self.max_cy = int(self.bottom // perception_radius) + 1
        self.cols = self.max_cx - self.min_cx + 3
        rows = self.max_cy - self.min_cy + 3
        self.cells: list[list[Creature]] = [[] for _ in range(self.cols * rows)]
        # Cells that have boids in them, so only those need clearing each frame.
        self.occupied_cells: list[list[Creature]] = []
        self.neighbor_offsets = tuple(
            dx + dy * self.cols for dy in DIRECTIONS for dx in DIRECTIONS
        )
        self.boids: list[Creature] = []
        # Velocity of each boid in pixels per second. This carries momentum between
        # frames, unlike Creature.velocity which is only the last frame's movement.
        self.velocities: dict[Creature, Vector] = {}

    def add_boids(self, boids: list[Creature]):
        self.boids.extend(boids)
        for boid in boids:
            # Start each boid moving in a random direction
            self.velocities[boid] = Vector.from_angle(
                random.uniform(0, 2 * math.pi),
                self.cruise_speed,
            )

    def cell_index(self, boid: Creature) -> int:
        cx = int(boid.x // self.perception_radius)
        cy = int(boid.y // self.perception_radius)
        cx = min(max(cx, self.min_cx), self.max_cx)
        cy = min(max(cy, self.min_cy), self.max_cy)
        # +1 skips the padding cell
        return (cx - self.min_cx + 1) + (cy - self.min_cy + 1) * self.cols

    def in_fov(
        self, dx: float, dy: float, dist_sq: float, dir_x: float, dir_y: float
    ) -> bool:
        """
        Is the neighbor at offset (dx, dy) inside the view cone of a boid facing
        (dir_x, dir_y)?
        """
        if self.fov_degrees >= 360:
            return True

        # A negative dot product means the neighbor is behind the boid
        dot_product = dx * dir_x + dy * dir_y

        if self.fov_degrees <= 180:
            # Narrow hemisphere in front of boid so ignore everything behind.
            if dot_product <= 0:
                return False

            return dot_product**2 >= dist_sq * self.cos_half_sq
        else:
            # Wider than 180, so we only remove a small cone behind.
            if dot_product >= 0:
                return True
            return dot_product**2 <= dist_sq * self.cos_half_sq

    def get_neighbors(self, boid: Creature) -> list[Creature]:
        """
        Get neighbors from the 3x3 cells around the boid in the spatial grid,
        removing the ones outside its field of view.

        For now we'll just return all of the neighbors as one. Maybe later we can
        support different radii for each force.
        """
        cells = self.cells
        index = self.cell_index(boid)
        neighbors = []

        bx = boid.x
        by = boid.y
        velocity = self.velocities[boid]
        speed = math.sqrt(velocity.x * velocity.x + velocity.y * velocity.y)
        if speed < 1e-9:
            dir_x = dir_y = 0.0
        else:
            dir_x = velocity.x / speed
            dir_y = velocity.y / speed

        for offset in self.neighbor_offsets:
            for other in cells[index + offset]:
                if other is boid:
                    continue

                dx = other.x - bx
                dy = other.y - by
                dist_sq = dx * dx + dy * dy
                # Same position has no direction to push or see
                if dist_sq == 0 or not self.in_fov(dx, dy, dist_sq, dir_x, dir_y):
                    continue

                neighbors.append(other)

        return neighbors

    def flock(self, boid: Creature, neighbors: list[Creature]) -> Vector:
        """
        Separation, alignment, and cohesion in a single pass over the neighbors.
        Uses plain floats in the loop to avoid allocating Vectors per neighbor.
        We combine the three forces so that we don't need to iterate over neighbors
        for each force individually.

        - Separation: move away from neighbors, closer ones pushing harder.
        - Alignment: match the average velocity of neighbors.
        - Cohesion: move towards the neighbors' center of mass.
        """
        if not neighbors:
            return Vector(0, 0)

        velocities = self.velocities
        bx = boid.x
        by = boid.y

        # Running totals, one set per force
        sep_x = sep_y = 0.0  # separation: sum of pushes away
        sum_vx = sum_vy = 0.0  # alignment: sum of neighbor velocities
        sum_dx = sum_dy = 0.0  # cohesion: sum of offsets to neighbors

        for other in neighbors:
            # Shared: offset to the neighbor, used by separation and cohesion
            dx = other.x - bx
            dy = other.y - by
            dist_sq = dx * dx + dy * dy

            # Separation: -offset / dist^2 is a unit vector away scaled by
            # 1/dist, so closer neighbors push harder.
            sep_x -= dx / dist_sq
            sep_y -= dy / dist_sq

            # Alignment
            other_velocity = velocities[other]
            sum_vx += other_velocity.x
            sum_vy += other_velocity.y

            # Cohesion: avg(offset) == avg(position) - boid position
            sum_dx += dx
            sum_dy += dy

        velocity = velocities[boid]
        inverse_count = 1.0 / len(neighbors)
        # Separation is a sum, alignment and cohesion are averages
        fx = (
            sep_x * self.separation_force
            + (sum_vx * inverse_count - velocity.x) * self.alignment_force
            + sum_dx * inverse_count * self.cohesion_force
        )
        fy = (
            sep_y * self.separation_force
            + (sum_vy * inverse_count - velocity.y) * self.alignment_force
            + sum_dy * inverse_count * self.cohesion_force
        )
        return Vector(fx, fy)

    def ease_in(self, distance_to_wall: float) -> float:
        """
        Ease the avoidance force in as a boid approaches a wall.
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

    def avoidance(self, boid: Creature) -> Vector:
        """
        Move boids away from obstacles such as the walls.
        The walls sit outside_window_size beyond each edge of the window, so a
        positive value lets boids swim off screen before turning back. We'll apply
        the avoidance force more as they get within wall_avoid_distance of a wall.
        """

        dx = self.ease_in(boid.x - self.left) - self.ease_in(self.right - boid.x)
        dy = self.ease_in(boid.y - self.top) - self.ease_in(self.bottom - boid.y)

        return Vector(dx, dy) * self.avoidance_force

    def cruise(self, boid: Creature) -> Vector:
        """
        Speed up or slow down along the current heading towards cruise_speed.
        """
        velocity = self.velocities[boid]
        speed = velocity.magnitude()
        if speed == 0:
            return Vector(0, 0)

        return velocity.with_mag((self.cruise_speed - speed) * self.cruise_force)

    def update(self, dt: float):
        """
        1. Clear previous grid and add all boids to grid
        2. For each boid, get neighbors and add separation, alignment, and cohesion
        3. Add avoidance
        4. Add noise and cruise
        5. Apply the summed forces as acceleration and clamp speed to [min_speed, max_speed]
        6. Move boid based on velocity
        """

        # 1. Clear grid and add all boids
        for cell in self.occupied_cells:
            cell.clear()
        self.occupied_cells.clear()
        for boid in self.boids:
            cell = self.cells[self.cell_index(boid)]
            if not cell:
                self.occupied_cells.append(cell)
            cell.append(boid)

        # Now that grid is computed, we can proceed with steps #2-5. Compute every new
        # velocity before moving anything so each boid sees the same snapshot.
        new_velocities: dict[Creature, Vector] = {}
        for boid in self.boids:
            # 2, 3: Separation, alignment, cohesion, avoidance
            neighbors = self.get_neighbors(boid)
            move_vec = self.flock(boid, neighbors)
            move_vec += self.avoidance(boid)

            # 4: Add random noise and pull back towards cruise speed
            move_vec += Vector(random.uniform(-1, 1), random.uniform(-1, 1))
            move_vec += self.cruise(boid)

            # 5. Apply forces as acceleration and clamp speed to [min_speed, max_speed]
            velocity = self.velocities[boid] + move_vec * dt
            speed = max(self.min_speed, min(velocity.magnitude(), self.max_speed))
            new_velocities[boid] = velocity.with_mag(speed)

        # 6. Move boids
        for boid in self.boids:
            self.velocities[boid] = new_velocities[boid]
            boid.move(new_velocities[boid] * dt)
            boid.render()
