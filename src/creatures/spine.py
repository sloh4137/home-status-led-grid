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
    ):
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
        self.palette = dio.Palette(2)
        self.palette.make_transparent(0)
        self.palette[1] = 0x2E9BFF
        self.bitmap = dio.Bitmap(10, 10, 256)
        self.grid = dio.TileGrid(
            self.bitmap, pixel_shader=self.palette, x=origin.x, y=origin.y
        )
        self.render()

    def position(self):
        return self.joints[0]

    def move(self, velocity: Vector):
        """
        Update the head position to the given argument then update all the joints accordingly.
        """

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

        # Find the top left and bottom right edges
        x_min, x_max = self.joints[0].x, self.joints[0].x
        y_min, y_max = self.joints[0].y, self.joints[0].y

        for vec in self.joints[1:]:
            x_min = min(x_min, vec.x)
            x_max = max(x_max, vec.x)
            y_min = min(y_min, vec.y)
            y_max = max(y_max, vec.y)

        bmp = dio.Bitmap(ceil(x_max - x_min) + 1, ceil(y_max - y_min) + 1, 256)
        for vec in self.joints:
            bitmap_x = floor(vec.x - x_min)
            bitmap_y = floor(vec.y - y_min)
            bmp[bitmap_x, bitmap_y] = 1

        self.grid.x = floor(x_min)
        self.grid.y = floor(y_max)
        self.grid.bitmap = bmp
