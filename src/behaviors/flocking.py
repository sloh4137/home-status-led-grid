import math
import random

from behaviors.behavior import Behavior
from creatures.creature import Creature

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
        # Cells hold boid indices into the flat lists below.
        self.cells: list[list[int]] = [[] for _ in range(self.cols * rows)]
        # Cells that have boids in them, so only those need clearing each frame.
        self.occupied_cells: list[list[int]] = []
        self.neighbor_offsets = tuple(
            dx + dy * self.cols for dy in DIRECTIONS for dx in DIRECTIONS
        )
        self.boids: list[Creature] = []
        # Flat per-boid state indexed by position in self.boids, so the hot loops
        # read plain floats instead of chasing Creature/Vector attributes.
        # These positions are the source of truth: the behavior integrates them each
        # frame and pushes them to the boids with Creature.set_state, rather than
        # reading positions back from the boids.
        self.xs: list[float] = []
        self.ys: list[float] = []
        # Velocity of each boid in pixels per second. This carries momentum between
        # frames, unlike Creature.velocity which is only the last frame's movement.
        self.vxs: list[float] = []
        self.vys: list[float] = []
        # Steering is only updated for half the boids each frame, alternating between
        # even and odd indices. Every boid still moves every frame.
        self.steer_parity = 0
        # Length of the previous frame, so steering can cover the time since each
        # boid was last steered (two frames ago).
        self.prev_dt = 0.0

    def add_boids(self, boids: list[Creature]):
        self.boids.extend(boids)
        for boid in boids:
            self.xs.append(boid.x)
            self.ys.append(boid.y)
            # Start each boid moving in a random direction
            angle = random.uniform(0, 2 * math.pi)
            self.vxs.append(math.cos(angle) * self.cruise_speed)
            self.vys.append(math.sin(angle) * self.cruise_speed)

    def cell_index(self, x: float, y: float) -> int:
        cx = int(x // self.perception_radius)
        cy = int(y // self.perception_radius)
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

    def get_neighbors(self, i: int) -> list[int]:
        """
        Get indices of the neighbors of boid i from the 3x3 cells around it in the
        spatial grid, removing the ones outside its field of view.

        For now we'll just return all of the neighbors as one. Maybe later we can
        support different radii for each force.
        """
        cells = self.cells
        xs = self.xs
        ys = self.ys
        bx = xs[i]
        by = ys[i]
        index = self.cell_index(bx, by)
        neighbors = []

        vx = self.vxs[i]
        vy = self.vys[i]
        speed = math.sqrt(vx * vx + vy * vy)
        if speed < 1e-9:
            dir_x = dir_y = 0.0
        else:
            dir_x = vx / speed
            dir_y = vy / speed

        for offset in self.neighbor_offsets:
            for j in cells[index + offset]:
                if j == i:
                    continue

                dx = xs[j] - bx
                dy = ys[j] - by
                dist_sq = dx * dx + dy * dy
                # Same position has no direction to push or see
                if dist_sq == 0 or not self.in_fov(dx, dy, dist_sq, dir_x, dir_y):
                    continue

                neighbors.append(j)

        return neighbors

    def flock(self, i: int, neighbors: list[int]) -> tuple[float, float]:
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
            return 0.0, 0.0

        xs = self.xs
        ys = self.ys
        vxs = self.vxs
        vys = self.vys
        bx = xs[i]
        by = ys[i]

        # Running totals, one set per force
        sep_x = sep_y = 0.0  # separation: sum of pushes away
        sum_vx = sum_vy = 0.0  # alignment: sum of neighbor velocities
        sum_dx = sum_dy = 0.0  # cohesion: sum of offsets to neighbors

        for j in neighbors:
            # Shared: offset to the neighbor, used by separation and cohesion
            dx = xs[j] - bx
            dy = ys[j] - by
            dist_sq = dx * dx + dy * dy

            # Separation: -offset / dist^2 is a unit vector away scaled by
            # 1/dist, so closer neighbors push harder.
            sep_x -= dx / dist_sq
            sep_y -= dy / dist_sq

            # Alignment
            sum_vx += vxs[j]
            sum_vy += vys[j]

            # Cohesion: avg(offset) == avg(position) - boid position
            sum_dx += dx
            sum_dy += dy

        inverse_count = 1.0 / len(neighbors)
        # Separation is a sum, alignment and cohesion are averages
        fx = (
            sep_x * self.separation_force
            + (sum_vx * inverse_count - vxs[i]) * self.alignment_force
            + sum_dx * inverse_count * self.cohesion_force
        )
        fy = (
            sep_y * self.separation_force
            + (sum_vy * inverse_count - vys[i]) * self.alignment_force
            + sum_dy * inverse_count * self.cohesion_force
        )
        return fx, fy

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

    def avoidance(self, x: float, y: float) -> tuple[float, float]:
        """
        Move boids away from obstacles such as the walls.
        The walls sit outside_window_size beyond each edge of the window, so a
        positive value lets boids swim off screen before turning back. We'll apply
        the avoidance force more as they get within wall_avoid_distance of a wall.
        """

        dx = self.ease_in(x - self.left) - self.ease_in(self.right - x)
        dy = self.ease_in(y - self.top) - self.ease_in(self.bottom - y)

        return dx * self.avoidance_force, dy * self.avoidance_force

    def update(self, dt: float):
        """
        1. Clear previous grid and add all boids to grid
        2. For half the boids (alternating each frame), get neighbors and add
           separation, alignment, and cohesion
        3. Add avoidance
        4. Add noise and cruise
        5. Apply the summed forces as acceleration and clamp speed to [min_speed, max_speed]
        6. Move boid based on velocity and push the new state to the creature
        """
        boids = self.boids
        count = len(boids)
        cells = self.cells
        xs = self.xs
        ys = self.ys
        vxs = self.vxs
        vys = self.vys

        # 1. Clear grid and add all boids
        for cell in self.occupied_cells:
            cell.clear()
        self.occupied_cells.clear()
        for i in range(count):
            cell = cells[self.cell_index(xs[i], ys[i])]
            if not cell:
                self.occupied_cells.append(cell)
            cell.append(i)

        # Now that grid is computed, we can proceed with steps #2-5. Compute every new
        # velocity before moving anything so each boid sees the same snapshot.
        # Only half the boids are steered this frame; the others keep their velocity.
        # Each steered boid was last steered two frames ago, so the forces are applied
        # over both frames.
        new_vxs = vxs[:]
        new_vys = vys[:]
        steer_dt = dt + self.prev_dt
        self.prev_dt = dt
        parity = self.steer_parity
        self.steer_parity = 1 - parity
        min_speed = self.min_speed
        max_speed = self.max_speed
        cruise_speed = self.cruise_speed
        cruise_force = self.cruise_force
        uniform = random.uniform
        for i in range(parity, count, 2):
            vx = vxs[i]
            vy = vys[i]

            # 2, 3: Separation, alignment, cohesion, avoidance
            fx, fy = self.flock(i, self.get_neighbors(i))
            ax, ay = self.avoidance(xs[i], ys[i])
            fx += ax
            fy += ay

            # 4: Add random noise and pull back towards cruise speed along the
            # current heading
            fx += uniform(-1, 1)
            fy += uniform(-1, 1)
            speed = math.sqrt(vx * vx + vy * vy)
            if speed != 0:
                scale = (cruise_speed - speed) * cruise_force / speed
                fx += vx * scale
                fy += vy * scale

            # 5. Apply forces as acceleration and clamp speed to [min_speed, max_speed]
            vx += fx * steer_dt
            vy += fy * steer_dt
            speed = math.sqrt(vx * vx + vy * vy)
            if speed != 0:
                scale = max(min_speed, min(speed, max_speed)) / speed
                vx *= scale
                vy *= scale
            new_vxs[i] = vx
            new_vys[i] = vy

        # 6. Move boids
        self.vxs = new_vxs
        self.vys = new_vys
        for i in range(count):
            vx = new_vxs[i]
            vy = new_vys[i]
            x = xs[i] + vx * dt
            y = ys[i] + vy * dt
            xs[i] = x
            ys[i] = y
            boid = boids[i]
            boid.set_state(x, y, vx, vy)
            boid.render()
