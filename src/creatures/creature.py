# Creatures define some movable, dynamic entity that can move around the screen.

from abc import ABC, abstractmethod

class Creature(ABC):

  @abstractmethod
  def update(self, dt: int):
    """
    Move the creature to the next step depending on how much time has passed (dt = delta time)
    """
    pass

  @abstractmethod
  def render(self):
    """
    Render the creature to the actual display.
    """

