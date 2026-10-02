"""
Tipos de datos geométricos del motor: posición (Point2D) y
dirección/desplazamiento/velocidad (Vector2D).
"""

import math
from dataclasses import dataclass


# Nota: @dataclass genera el __init__; con frozen=True además bloquea
# la asignación de atributos después de construir el objeto.
@dataclass(frozen=True)
class Vector2D:
    """Dirección, desplazamiento o velocidad."""

    x: float
    y: float

    def magnitude(self) -> float:
        """
        @brief Devuelve la rapidez o fuerza del vector (su longitud/escalar).
        Útil para calcular la velocidad independientemente de su dirección.
        """
        return math.hypot(self.x, self.y)

    def normalize(self) -> "Vector2D":
        """
        @brief Devuelve un vector de magnitud 1 en la misma dirección (vector unitario).
        Útil para calcular hacia donde va un objetivo.

        Caso vector cero: si la magnitud es 0 devuelve Vector2D(0, 0)
        (no lanza ZeroDivisionError).
        """
        magn = self.magnitude()
        if magn == 0:
            return Vector2D(0.0, 0.0)
        return Vector2D(self.x / magn, self.y / magn)


@dataclass(frozen=True)
class Point2D:
    """Punto espacial o posición fija en el plano de la cancha."""

    x: float
    y: float

    def _vector_to(self, other: "Point2D") -> Vector2D:
        """Vector que va desde este punto hasta `other` (other - self)."""
        return Vector2D(other.x - self.x, other.y - self.y)

    def distance_to(self, other: "Point2D") -> float:
        """
        @brief Calcula la distancia hacia otro Point2D.
        @param other Point2D a calcular la distancia.
        """
        return self._vector_to(other).magnitude()

    def direction_to(self, target: "Point2D") -> Vector2D:
        """
        @brief Retorna el Vector2D de dirección que apunta hacia 'target'.

        Si target es el mismo punto devuelve Vector2D(0, 0).
        """
        return self._vector_to(target).normalize()