"""
Tipos de datos del contrato de Primitivas: AttributeType y GameState.
"""

from dataclasses import dataclass
from enum import Enum

from src.engine.geometry_types import Point2D, Vector2D


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

    # tener en cuenta que frozen=True no protege las listas de teammates/opponents; el builder debe entregar copias (en snapshot.py)
