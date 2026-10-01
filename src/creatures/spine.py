# Basic chain representing the spine of a creature

from math import pi, ceil, floor
from graphics.vector import Vector, constrain_angle
from creatures.creature import Creature


class CreatureSpine(Creature):
    COLOR = 0x2E9BFF

    def __init__(
        self,
        origin: Vector,
        num_joints: int,
        link_size: int,
        angle_constraint: float = 2 * pi,
        render_padding: int = 0,
        color_index: int = 1,
    ):
        # Palette index to draw with
        self.color_index = color_index
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

        # No joint can be further than the spine's length from the head, so that bounds
        # the drawing however it bends. render_padding adds room for anything drawn
        # around the joints (e.g. body width).
        self.render_radius = ceil((num_joints - 1) * link_size) + render_padding

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

    def render(self, bitmap):
        """
        Render the chain as a series of pixels.
        """
        width = bitmap.width
        height = bitmap.height
        color_index = self.color_index
        for vec in self.joints:
            x = floor(vec.x)
            y = floor(vec.y)
            # Real displayio raises IndexError on out-of-range writes
            if 0 <= x < width and 0 <= y < height:
                bitmap[x, y] = color_index
