"""
Tipos de datos utilizados por el motor de simulación
"""

from dataclasses import dataclass
from enum import Enum
import math
from typing import Optional


# ====================================== TIPOS GEOMÉTRICOS ==========================================
# Incluyen: Vector2D, Point2D.
# ===================================================================================================

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


# ====================================== TIPOS DE CONTEXTO  ==========================================
# Incluyen: AttributeType, GameState
# ====================================================================================================

class AttributeType(Enum):
    """Tipo de atributo de un jugador."""

    POWER = "POWER"
    AGILITY = "AGILITY"
    CONTROL = "CONTROL"
    SPEED = "SPEED"
    STRENGTH = "STRENGTH"


@dataclass(frozen=True)
class GameState:
    """Información del juego visible para un jugador en el tick actual."""

    ball_position: Point2D    # Posición en cancha de la pelota
    ball_velocity: Vector2D   # Velocidad inmediata de la pelota
    my_position: Point2D      # Posición en cancha del jugador
    teammates: list[Point2D]  # Posiciones de los compañeros del jugador
    opponents: list[Point2D]  # Posiciones de los rivales del jugador
    team_goal: Point2D        # Posición del arco aliado
    opponent_goal: Point2D    # Posición del arco rival

    # tener en cuenta que frozen=True no protege las listas de teammates/opponents; el builder debe entregar copias mediante snapshots.

# ====================================== TIPOS DE INTENCIÓN ==========================================
# Incluyen: ActionType, Intention
# ====================================================================================================

class ActionType(Enum):
    """
    Valores de las acciones del jugador. 
    Coinciden con `current_action` del contrato.
    """

    IDLE = "idle"
    RUN_TO = "run_to"
    KICK_BALL = "kick_ball"


@dataclass(frozen=True)
class Intention:
    """
    Acción + parámetros. Un solo dataclass con campos opcionales: los
    campos que no aplican a la acción quedan en None.
      - IDLE: sin parámetros.
      - RUN_TO: target, speed_percentage.
      - KICK_BALL: direction, power_percentage.
    """

    action: ActionType
    target: Optional[Point2D] = None
    speed_percentage: Optional[float] = None
    direction: Optional[Vector2D] = None
    power_percentage: Optional[float] = None