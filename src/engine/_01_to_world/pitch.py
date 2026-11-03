"""
Medidas y reglas fijas de la cancha: tamaño, arcos, cuándo hay gol y dónde arranca cada jugador.
No guarda nada de ningún partido: son datos y reglas que no cambian.
Ver más info. en Documentación - "ABOUT_DESIGN"
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.engine._01_to_world.data_types import Point2D

# =============== Medidas de la cancha (en metros) ===============

PITCH_LENGTH = 105.0  # largo (eje x): de la línea de fondo de HOME (x=0) a la del AWAY (x=105)
PITCH_WIDTH = 60.0    # ancho (eje y): de 0 a 60, con el centro en y=30
GOAL_WIDTH = 7.32     # ancho del arco, centrado en y = PITCH_WIDTH / 2

# =============== Lados, arcos y deteccion de gol ===============

class TeamSide(Enum):
    """Lado de cancha que defiende cada equipo"""

    # Dos lados: HOME defiende x=0 y ataca hacia x=PITCH_LENGTH; AWAY es el espejo.
    HOME = "HOME"
    AWAY = "AWAY"

@dataclass(frozen=True)
class GoalArea:
    """ 
    Tramo del arco sobre una línea de fondo, se usa para detectar goles.
    Es un rango de "y" entre los dos postes (no un punto: el punto está en goal_center).
    Ver más info. en Documentación - "ABOUT_DESIGN"
    """
    line_x: float       # x de la linea de fonde donde esta el arco
    post_min_y: float   # y del poste menor 
    post_max_y: float   # y del poste mayor 

    def contains_y(self, y: float) -> bool:
        """True si `y` cae dentro de los postes (postes inclusive)"""
        return self.post_min_y <= y <= self.post_max_y


def _goal_area(line_x: float) -> GoalArea:
    """ 
    Crea el arco de la línea x de fondo.
    """
    half_width = GOAL_WIDTH / 2
    center_y = PITCH_WIDTH / 2
    return GoalArea(line_x=line_x, post_min_y=center_y - half_width, post_max_y=center_y + half_width)


HOME_GOAL = _goal_area(0.0)           # arco que defiende HOME
AWAY_GOAL = _goal_area(PITCH_LENGTH)  # arco que defiende AWAY


def goal_center(side: TeamSide) -> Point2D:
    """Punto central del arco que defiende `side` (para GameState.team_goal)."""
    area = HOME_GOAL if side is TeamSide.HOME else AWAY_GOAL
    return Point2D(area.line_x, PITCH_WIDTH / 2)


def opponent_goal_center(side: TeamSide) -> Point2D:
    """Punto central del arco rival de `side` (para GameState.opponent_goal)."""
    other = TeamSide.AWAY if side is TeamSide.HOME else TeamSide.HOME
    return goal_center(other)


def detect_goal(ball_position: Point2D) -> Optional[TeamSide]:
    """ 
    Devuelve el lado que convierte el gol (no el que lo recibe), o None si no hay gol.
    Hay gol cuando la pelota llega a una línea de fondo dentro del ancho del arco
    Ver más info. en Documentación - "ABOUT_DESIGN"
    """
    
    # pelota en el arco que defiende HOME -> gol de AWAY
    if ball_position.x <= HOME_GOAL.line_x and HOME_GOAL.contains_y(ball_position.y):
        return TeamSide.AWAY
    # pelota en el arco que defiende AWAY -> gol de HOME
    if ball_position.x >= AWAY_GOAL.line_x and AWAY_GOAL.contains_y(ball_position.y):
        return TeamSide.HOME
    return None

# =============== Posiciones iniciales ===============

# Posicion inicial de cada rol, por formación: FORMATION_POSITIONS[formación][rol]
# Están definidas para el lado HOME (ataca hacia x creciente); starter_position las rota 
# para el lado AWAY. Cada equipo arranca en su propia mitad.
FORMATION_POSITIONS: dict[str, dict[str, Point2D]] = {
    "2-1": {
        "DEF_LEFT": Point2D(25.0, 15.0),
        "DEF_RIGHT": Point2D(25.0, 45.0),
        "FORWARD": Point2D(45.0, 30.0),
    },
    "1-2": {
        "DEFENDER": Point2D(25.0, 30.0),
        "FORWARD_LEFT": Point2D(45.0, 15.0),
        "FORWARD_RIGHT": Point2D(45.0, 45.0),
    },
}

BALL_INITIAL_POSITION = Point2D(PITCH_LENGTH / 2, PITCH_WIDTH / 2)  # centro de la cancha


def mirror_position(position: Point2D) -> Point2D:
    """Gira una posición 180° respecto del centro de la cancha."""
    return Point2D(PITCH_LENGTH - position.x, PITCH_WIDTH - position.y)


def opposite_side(side: TeamSide) -> TeamSide:
    """El lado contrario a `side`."""
    return TeamSide.AWAY if side is TeamSide.HOME else TeamSide.HOME


def starter_position(formation_type: str, role: str, side: TeamSide) -> Point2D:
    """
    Posición inicial de un titular según su formación, rol y lado.
    """
    base = FORMATION_POSITIONS[formation_type][role]    # posición definida para HOME
    if side is TeamSide.HOME:
        return base
    # AWAY se gira la posición 180° respecto del centro de la cancha.
    # Así cada rol mantiene su lado respecto de su propio equipo.
    return mirror_position(base)