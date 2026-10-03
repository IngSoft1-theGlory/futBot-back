"""
Intention: lo que un jugador quiere hacer en un tick.
Las primitivas solo REGISTRAN una intención; el resolver la aplica.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.engine.geometry_types import Point2D, Vector2D


class ActionType(Enum):
    """Valores coinciden con `current_action` del contrato."""

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
