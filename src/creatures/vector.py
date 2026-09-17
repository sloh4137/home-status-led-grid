from dataclasses import dataclass
from math import sqrt, atan2, copysign, cos, sin, tau, pi


@dataclass(slots=True, frozen=True)
class Vector:
    x: float
    y: float

    def add(self, other: Vector) -> Vector:
        return Vector(self.x + other.x, self.y + other.y)

    def __add__(self, other: Vector) -> Vector:
        return Vector(self.x + other.x, self.y + other.y)

    def sub(self, other: Vector) -> Vector:
        return Vector(self.x - other.x, self.y - other.y)

    def __sub__(self, other: Vector) -> Vector:
        return Vector(self.x - other.x, self.y - other.y)

    def __mul__(self, s: float) -> Vector:
        return Vector(self.x * s, self.y * s)

    __rmul__ = __mul__

    def magnitude(self) -> float:
        return sqrt(self.x**2 + self.y**2)

    def normalized(self) -> Vector:
        mag = self.magnitude()
        if mag < 1e-9:
            return Vector(0, 0)

        return Vector(self.x / mag, self.y / mag)

    def heading(self) -> float:
        return atan2(self.y, self.x)

    def with_mag(self, mag: float) -> Vector:
        """
        Creates a new Vector in the same direction but with the given magnitude
        """
        m = self.magnitude()
        if m == 0:
            return self
        s = mag / m
        return Vector(self.x * s, self.y * s)

    def copy(self) -> Vector:
        return Vector(self.x, self.y)

    @classmethod
    def from_angle(cls, angle: float, mag: float = 1.0) -> Vector:
        return cls(mag * cos(angle), mag * sin(angle))


def simplify_angle(angle: float) -> float:
    """Wrap to [0, 2pi)"""
    return angle % tau


def relative_angle_diff(angle: float, anchor: float) -> float:
    """How many radians to turn `angle` to reach `anchor`? Result in (-pi, pi]"""

    return (anchor - angle + pi) % tau - pi


def constrain_angle(angle: float, anchor: float, constraint: float) -> float:
    """Clamp angle to be within `constraint` radians of anchor."""
    diff = relative_angle_diff(angle, anchor)  # anchor - angle

    if abs(diff) <= constraint:
        return simplify_angle(angle)

    # clamp to nearest edge
    return simplify_angle(anchor - copysign(constraint, diff))


def constrain_distance(pos: Vector, anchor: Vector, constraint: float) -> Vector:
    return anchor.add(pos.sub(anchor).with_mag(constraint))
