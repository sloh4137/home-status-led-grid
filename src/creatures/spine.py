# Basic chain representing the spine of a creature

from math import pi, ceil, floor, sqrt, cos, sin
from graphics.vector import Vector
from creatures.creature import Creature


class CreatureSpine(Creature):
    """
    A follow-the-leader chain of joints, link_size apart.

    The joints are kept as plain floats in flat lists so a frame allocates
    nothing (see OPTIMIZATIONS.md):

    - jx[i], jy[i]: joint i's position. Joint 0 is the head.
    - ux[i], uy[i]: unit direction joint i faces. For the head it is the
      direction of travel; for joint i > 0 it points from joint i to joint
      i - 1. This replaces per-joint angles: anything that needs a joint's
      direction (spots, sprite parts) reads it from here, and only a sprite
      part needs an atan2 at its own joint.

    Each joint's direction is kept within angle_constraint of the joint ahead
    of it. The check is a dot product against cos(angle_constraint), and the
    clamp is a rotation by the precomputed cos/sin, so neither needs trig.
    """

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
        self.link_size = link_size
        self.angle_constraint = angle_constraint
        # A limit of pi or more never binds (no turn is sharper than pi), so
        # disable the check with a cosine no dot product can be below.
        if angle_constraint >= pi:
            self._cos_limit = -2.0
        else:
            self._cos_limit = cos(angle_constraint)
        self._sin_limit = sin(angle_constraint)

        # Last frame's movement, as move() reports it through velocity
        self._dx = 0.0
        self._dy = 0.0

        # Create all the joints link_size apart, trailing down from the head,
        # so each one faces up towards the joint ahead of it.
        ox = origin.x
        oy = origin.y
        self.jx = [ox] * num_joints
        self.jy = [oy + i * link_size for i in range(num_joints)]
        self.ux = [0.0] * num_joints
        self.uy = [-1.0] * num_joints

        # No joint can be further than the spine's length from the head, so that bounds
        # the drawing however it bends. render_padding adds room for anything drawn
        # around the joints (e.g. body width).
        self.render_radius = ceil((num_joints - 1) * link_size) + render_padding

    def position(self):
        return Vector(self.jx[0], self.jy[0])

    @property
    def x(self) -> float:
        return self.jx[0]

    @property
    def y(self) -> float:
        return self.jy[0]

    @property
    def velocity(self) -> Vector:
        return Vector(self._dx, self._dy)

    def move(self, velocity: Vector):
        """
        Move the head by velocity, then let the rest of the joints follow.
        """
        self.set_state(
            self.jx[0] + velocity.x, self.jy[0] + velocity.y, velocity.x, velocity.y
        )

    def set_state(self, x: float, y: float, vx: float, vy: float):
        """
        Put the head at (x, y) and let the rest of the joints follow. The
        direction of travel comes from how far the head moved, so (vx, vy) is
        not needed.
        """
        jx = self.jx
        jy = self.jy
        ux = self.ux
        uy = self.uy

        # Head: face the way it moved. Keep the last direction when it didn't
        # move, since a zero vector has no direction.
        dx = x - jx[0]
        dy = y - jy[0]
        self._dx = dx
        self._dy = dy
        d = sqrt(dx * dx + dy * dy)
        if d > 1e-9:
            ax = dx / d
            ay = dy / d
            ux[0] = ax
            uy[0] = ay
        else:
            ax = ux[0]
            ay = uy[0]
        jx[0] = x
        jy[0] = y

        link = self.link_size
        cos_limit = self._cos_limit
        sin_limit = self._sin_limit
        px = x
        py = y
        for i in range(1, len(jx)):
            # Direction from this joint to the one ahead
            dx = px - jx[i]
            dy = py - jy[i]
            d = sqrt(dx * dx + dy * dy)
            if d > 1e-9:
                dx /= d
                dy /= d
            else:
                # On top of the joint ahead: line up behind it
                dx = ax
                dy = ay

            # Too sharp a bend from the joint ahead (ax, ay): rotate that
            # direction by the limit towards this one. The cross product's
            # sign says which way.
            if dx * ax + dy * ay < cos_limit:
                if ax * dy - ay * dx >= 0:
                    s = sin_limit
                else:
                    s = -sin_limit
                dx = ax * cos_limit - ay * s
                dy = ax * s + ay * cos_limit

            ux[i] = dx
            uy[i] = dy
            px -= dx * link
            py -= dy * link
            jx[i] = px
            jy[i] = py
            ax = dx
            ay = dy

    def render(self, bitmap):
        """
        Render the chain as a series of pixels.
        """
        width = bitmap.width
        height = bitmap.height
        color_index = self.color_index
        jx = self.jx
        jy = self.jy
        for i in range(len(jx)):
            x = floor(jx[i])
            y = floor(jy[i])
            # Real displayio raises IndexError on out-of-range writes
            if 0 <= x < width and 0 <= y < height:
                bitmap[x, y] = color_index
