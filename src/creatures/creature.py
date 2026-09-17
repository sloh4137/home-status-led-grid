# Creatures define some movable, dynamic entity that can move around the screen.

from abc import ABC, abstractmethod
from creatures.vector import Vector


class Creature(ABC):

    @abstractmethod
    def getPos(self) -> Vector:
        """
        Get the primary position of the creature we'll use for behavior calculations.
        """

    @abstractmethod
    def move(self, velocity: Vector):
        """
        Move the creature by velocity.
        """
        pass

    @abstractmethod
    def render(self):
        """
        Render the creature to the actual display.
        """
