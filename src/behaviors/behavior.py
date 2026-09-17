from abc import ABC, abstractmethod


class Behavior(ABC):
    @abstractmethod
    def update(self, dt: float):
        pass
