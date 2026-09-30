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

    def render(self):
        """
        Render the creature to the actual display.
        """
        raise NotImplementedError
