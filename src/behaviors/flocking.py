import math
import random

from behaviors.swim import SwimBehavior

DIRECTIONS = (-1, 0, 1)

# How the field of view is checked, picked once from fov_degrees
FOV_ALL = 0  # >= 360: sees everything
FOV_FRONT = 1  # <= 180: a cone in front, nothing behind
FOV_WIDE = 2  # > 180: everything except a cone behind


class FlockingBehavior(SwimBehavior):
    def __init__(
        self,
        bitmap,
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
        random_steer: int,
        min_speed: float,
        max_speed: float,
        cruise_speed: float,
        cruise_force: float,
        grid_min_boids: int = 24,
        steer_half: bool = True,
    ):
        """
        Flocking (separation, alignment, cohesion) for a group of boids.

        grid_min_boids: below this many boids, each steered boid checks every
        other boid directly; at or above it, the spatial grid is used. Both paths
        flock with the same neighbours (within perception_radius and the field of
        view), so the threshold only changes the speed.

        steer_half: steer only half the boids each frame, alternating between even
        and odd indices. Every boid still moves every frame.
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

        # How much the boids can see
        self.perception_radius = perception_radius
        self.fov_degrees = fov_degrees
        self.cos_half_sq = math.cos(math.radians(fov_degrees / 2)) ** 2
        if fov_degrees >= 360:
            self.fov_mode = FOV_ALL
        elif fov_degrees <= 180:
            self.fov_mode = FOV_FRONT
        else:
            self.fov_mode = FOV_WIDE

        # Forces that act on the boid
        self.separation_force = separation_force
        self.alignment_force = alignment_force
        self.cohesion_force = cohesion_force
        self.random_steer = random_steer
        # cruise_force is how quickly (per second) boids drift back to
        # cruise_speed after being slowed down or sped up by other forces.
        self.cruise_force = cruise_force

        self.grid_min_boids = grid_min_boids
        self.steer_half = steer_half

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
        # Index of cell (0, 0), so a cell's index is cell_origin + cx + cy * cols.
        # +1 skips the padding cell.
        self.cell_origin = (1 - self.min_cx) + (1 - self.min_cy) * self.cols
        # Cells hold boid indices into the flat lists.
        self.cells: list[list[int]] = [[] for _ in range(self.cols * rows)]
        # Cells that have boids in them, so only those need clearing each frame.
        self.occupied_cells: list[list[int]] = []
        self.neighbor_offsets = tuple(
            dx + dy * self.cols for dy in DIRECTIONS for dx in DIRECTIONS
        )
        # Alternates between even (0) and odd (1) boids when steer_half is on
        self.steer_parity = 0
        # Length of the previous frame, so steering can cover the time since each
        # boid was last steered (two frames ago).
        self.prev_dt = 0.0

    def cell_index(self, x: float, y: float) -> int:
        """
        Get the int index for the cell. Unused as a method and in-lining this computation instead
        since function calls are expensive in CircuitPython.
        """
        cx = int(x // self.perception_radius)
        cy = int(y // self.perception_radius)
        cx = min(max(cx, self.min_cx), self.max_cx)
        cy = min(max(cy, self.min_cy), self.max_cy)
        # +1 skips the padding cell
        return (cx - self.min_cx + 1) + (cy - self.min_cy + 1) * self.cols

    def _build_grid(self, count: int):
        """
        Clear the grid and put every boid in its cell.
        """
        cells = self.cells
        occupied = self.occupied_cells
        for cell in occupied:
            cell.clear()
        occupied.clear()
        xs = self.xs
        ys = self.ys
        radius = self.perception_radius
        min_cx = self.min_cx
        max_cx = self.max_cx
        min_cy = self.min_cy
        max_cy = self.max_cy
        cols = self.cols
        cell_origin = self.cell_origin
        for i in range(count):
            # Inlined cell_index(xs[i], ys[i]). Only boids that overshoot the swim
            # area need clamping, so the min/max calls are skipped for the rest.
            cx = int(xs[i] // radius)
            cy = int(ys[i] // radius)
            if not (min_cx <= cx <= max_cx and min_cy <= cy <= max_cy):
                cx = min(max(cx, min_cx), max_cx)
                cy = min(max(cy, min_cy), max_cy)
            cell = cells[cell_origin + cx + cy * cols]
            if not cell:
                occupied.append(cell)
            cell.append(i)

    def _steer(self, dt: float):
        """
        For the boids steered this frame (half of them, alternating, or all):
        1. Separation, alignment and cohesion, from one pass over the neighbours
           within perception_radius and the field of view. Below grid_min_boids
           the candidates are every boid; otherwise the 3x3 grid cells around it.
        2. Avoidance, near the walls only
        3. Random noise and a pull back towards cruise speed
        4. Apply the forces as acceleration over the time since the boid was last
           steered, and clamp speed to [min_speed, max_speed]

        Every new velocity is computed before any is stored, so each boid sees the
        same snapshot.
        """
        count = len(self.creatures)
        xs = self.xs
        ys = self.ys
        vxs = self.vxs
        vys = self.vys

        # Candidate neighbours of a boid are every j in source[base + offset] for
        # offset in offsets. Direct: one group holding every boid. Grid: the 3x3
        # cells around the boid's cell, with base set per boid.
        use_grid = count >= self.grid_min_boids
        if use_grid:
            self._build_grid(count)
            source = self.cells
            offsets = self.neighbor_offsets
        else:
            source = (range(count),)
            offsets = (0,)
        base = 0

        new_vxs = vxs[:]
        new_vys = vys[:]
        if self.steer_half:
            step = 2
            start = self.steer_parity
            self.steer_parity = 1 - start
            # Each steered boid was last steered two frames ago
            steer_dt = dt + self.prev_dt
            self.prev_dt = dt
        else:
            step = 1
            start = 0
            steer_dt = dt

        radius = self.perception_radius
        radius_sq = radius * radius
        min_cx = self.min_cx
        max_cx = self.max_cx
        min_cy = self.min_cy
        max_cy = self.max_cy
        cols = self.cols
        cell_origin = self.cell_origin
        fov_mode = self.fov_mode
        cos_half_sq = self.cos_half_sq
        separation_force = self.separation_force
        alignment_force = self.alignment_force
        cohesion_force = self.cohesion_force
        min_speed = self.min_speed
        max_speed = self.max_speed
        cruise_speed = self.cruise_speed
        cruise_force = self.cruise_force
        safe_left = self.safe_left
        safe_right = self.safe_right
        safe_top = self.safe_top
        safe_bottom = self.safe_bottom
        random_steer = self.random_steer
        uniform = random.uniform
        sqrt = math.sqrt
        for i in range(start, count, step):
            bx = xs[i]
            by = ys[i]
            vx = vxs[i]
            vy = vys[i]
            speed = sqrt(vx * vx + vy * vy)
            if speed < 1e-9:
                dir_x = dir_y = 0.0
            else:
                dir_x = vx / speed
                dir_y = vy / speed

            if use_grid:
                # Inlined cell_index(bx, by), clamping only boids that overshoot
                cx = int(bx // radius)
                cy = int(by // radius)
                if not (min_cx <= cx <= max_cx and min_cy <= cy <= max_cy):
                    cx = min(max(cx, min_cx), max_cx)
                    cy = min(max(cy, min_cy), max_cy)
                base = cell_origin + cx + cy * cols

            # 1. Running totals, one set per force
            n = 0
            sep_x = sep_y = 0.0  # separation: sum of pushes away
            sum_vx = sum_vy = 0.0  # alignment: sum of neighbor velocities
            sum_dx = sum_dy = 0.0  # cohesion: sum of offsets to neighbors
            for offset in offsets:
                for j in source[base + offset]:
                    dx = xs[j] - bx
                    dy = ys[j] - by
                    dist_sq = dx * dx + dy * dy
                    # Also skips the boid itself, and any boid at the same
                    # position, which has no direction to push or see
                    if dist_sq > radius_sq or dist_sq == 0:
                        continue
                    # Inlined field of view check. A negative dot product means
                    # the neighbor is behind the boid.
                    if fov_mode:
                        dot = dx * dir_x + dy * dir_y
                        if fov_mode == FOV_FRONT:
                            if dot <= 0 or dot * dot < dist_sq * cos_half_sq:
                                continue
                        elif dot < 0 and dot * dot > dist_sq * cos_half_sq:
                            continue

                    n += 1
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

            if n:
                inverse_count = 1.0 / n
                # Separation is a sum, alignment and cohesion are averages
                fx = (
                    sep_x * separation_force
                    + (sum_vx * inverse_count - vx) * alignment_force
                    + sum_dx * inverse_count * cohesion_force
                )
                fy = (
                    sep_y * separation_force
                    + (sum_vy * inverse_count - vy) * alignment_force
                    + sum_dy * inverse_count * cohesion_force
                )
            else:
                fx = fy = 0.0

            # 2. Avoidance is zero unless the boid is within wall_avoid_distance of
            # a wall
            if not (safe_left < bx < safe_right and safe_top < by < safe_bottom):
                ax, ay = self.avoidance(bx, by)
                fx += ax
                fy += ay

            # 3. Random noise and a pull back towards cruise speed along the
            # current heading
            fx += uniform(-random_steer, random_steer)
            fy += uniform(-random_steer, random_steer)
            if speed != 0:
                scale = (cruise_speed - speed) * cruise_force / speed
                fx += vx * scale
                fy += vy * scale

            # 4. Apply forces as acceleration and clamp speed
            vx += fx * steer_dt
            vy += fy * steer_dt
            speed = sqrt(vx * vx + vy * vy)
            if speed != 0:
                scale = max(min_speed, min(speed, max_speed)) / speed
                vx *= scale
                vy *= scale
            new_vxs[i] = vx
            new_vys[i] = vy

        self.vxs = new_vxs
        self.vys = new_vys
