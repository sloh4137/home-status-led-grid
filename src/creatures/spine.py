# Basic chain representing the spine of a creature

from math import pi, ceil, floor
from graphics.vector import Vector, constrain_angle
from creatures.creature import Creature

from _dio import dio


class CreatureSpine(Creature):
    def __init__(
        self,
        origin: Vector,
        num_joints: int,
        link_size: int,
        angle_constraint: float = 2 * pi,
        render_padding: int = 0,
    ):
        self._velocity = Vector(0, 0)
        self.link_size = link_size
        self.angle_constraint = angle_constraint

        # Create all the joints link_size apart
        self.joints = [origin]
        self.angles = [0.0] * num_joints
        link_size_vec = Vector(0, link_size)
        for i in range(1, num_joints):
            prev_joint = self.joints[i - 1]
            self.joints.append(prev_joint + link_size_vec)

        # Graphics
        # displayio can't swap in a bitmap of a different size, so allocate one fixed-size
        # bitmap centered on the head. No joint can be further than the spine's length from
        # the head, so it fits the whole creature however it bends. render_padding adds room
        # for anything drawn around the joints (e.g. body width).
        self.half_size = ceil((num_joints - 1) * link_size) + render_padding
        self.render_radius = self.half_size
        size = 2 * self.half_size + 1
        self.palette = self.make_palette()
        self.bitmap = dio.Bitmap(size, size, 256)
        self.grid = dio.TileGrid(self.bitmap, pixel_shader=self.palette)
        self.update_grid_position()

    def make_palette(self):
        palette = dio.Palette(2)
        palette.make_transparent(0)
        palette[1] = 0x2E9BFF
        return palette

    def update_grid_position(self):
        """Center the bitmap on the head."""
        self.grid.x = floor(self.joints[0].x) - self.half_size
        self.grid.y = floor(self.joints[0].y) - self.half_size

    def position(self):
        return self.joints[0]

    @property
    def velocity(self) -> Vector:
        return self._velocity

    def move(self, velocity: Vector):
        """
        Update the head position to the given argument then update all the joints accordingly.
        """
        self._velocity = velocity

        # Move the head to the given position
        head_pos = self.joints[0] + velocity
        self.angles[0] = (head_pos - self.joints[0]).heading()
        self.joints[0] = head_pos

        for i in range(1, len(self.joints)):
            prev_vector = self.joints[i - 1]
            prev_angle = self.angles[i - 1]

            cur_angle = (prev_vector - self.joints[i]).heading()
            constrained_angle = constrain_angle(
                cur_angle, prev_angle, self.angle_constraint
            )
            self.angles[i] = constrained_angle
            self.joints[i] = prev_vector - Vector.from_angle(
                constrained_angle, self.link_size
            )

    def render(self):
        """
        Render the chain as a series of pixels.
        """
        self.update_grid_position()
        self.bitmap.fill(0)
        for vec in self.joints:
            x = floor(vec.x) - self.grid.x
            y = floor(vec.y) - self.grid.y
            if 0 <= x < self.bitmap.width and 0 <= y < self.bitmap.height:
                self.bitmap[x, y] = 1
