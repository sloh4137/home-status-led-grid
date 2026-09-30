# Creatures define some movable, dynamic entity that can move around the screen.

from graphics.vector import Vector


class Creature:

    def position(self) -> Vector:
        """
        Get the primary position of the creature we'll use for behavior calculations.
        """
        raise NotImplementedError

    @property
    def x(self) -> float:
        return self.position().x

    @property
    def y(self) -> float:
        return self.position().y

    @property
    def velocity(self) -> Vector:
        raise NotImplementedError

    def move(self, velocity: Vector):
        """
        Move the creature by velocity.
        """
        raise NotImplementedError

    def set_state(self, x: float, y: float, vx: float, vy: float):
        """
        Put the creature at (x, y) moving with velocity (vx, vy) in pixels per
        second. Used by behaviors that track positions themselves, like flocking.

        The default moves by the offset from the current position, so any creature
        that implements move() works. Override this when the creature can store the
        state directly without allocating Vectors.
        """
        position = self.position()
        self.move(Vector(x - position.x, y - position.y))

    def render(self):
        """
        Render the creature to the actual display.
        """
        raise NotImplementedError
