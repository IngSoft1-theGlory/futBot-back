"""
Geometría fija de la cancha: dimensiones, arcos y posiciones iniciales
por formación/rol/lado.

- PITCH_LENGTH / PITCH_WIDTH: ya aparecían implícitas en los tests de
resolve.py y player_api.py (team_goal=Point2D(0,30), opponent_goal=
Point2D(105,30)). Las mantenemos para no romper esos tests.
- GOAL_WIDTH: ancho de arco FIFA 7.32m, reescalado a esta cancha.
- FORMATION_POSITIONS: posiciones de ejemplo, razonables pero arbitrarias.

GameState.team_goal / opponent_goal son un único Point2D: sirven para que un comportamiento
calcule hacia dónde patear (`direction_to`), no para detectar el gol.
Para detectar el gol hace falta un RANGO (el ancho del arco), que acá
modelamos aparte como GoalArea. GoalArea es un detalle INTERNO del
motor: nunca se expone a los comportamientos (no es parte de GameState).
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.engine.geometry_types import Point2D

PITCH_LENGTH = 105.0  # eje x: 0 (línea de fondo de HOME) a 105 (línea de AWAY)
PITCH_WIDTH = 60.0    # eje y: 0 a 60, centro en 30
GOAL_WIDTH = 7.32     # ancho del arco, centrado en y = PITCH_WIDTH / 2


class TeamSide(Enum):
    """Lado de cancha que defiende cada equipo. HOME defiende la línea
    x=0 y ataca hacia x=PITCH_LENGTH; AWAY es el espejo."""

    HOME = "HOME"
    AWAY = "AWAY"


@dataclass(frozen=True)
class GoalArea:
    """
    Segmento del arco sobre una línea de fondo, para detectar goles.
    No confundir con GameState.team_goal/opponent_goal (un solo punto,
    para apuntar al patear): esto es un rango de y, en una x fija.
    """

    line_x: float
    post_min_y: float
    post_max_y: float

    def contains_y(self, y: float) -> bool:
        """True si `y` cae dentro del ancho del arco (entre los dos postes)."""
        return self.post_min_y <= y <= self.post_max_y


def _goal_area(line_x: float) -> GoalArea:
    half_width = GOAL_WIDTH / 2
    center_y = PITCH_WIDTH / 2
    return GoalArea(line_x=line_x, post_min_y=center_y - half_width, post_max_y=center_y + half_width)


HOME_GOAL = _goal_area(0.0)           # arco que defiende HOME
AWAY_GOAL = _goal_area(PITCH_LENGTH)  # arco que defiende AWAY


def goal_center(side: TeamSide) -> Point2D:
    """Punto único del arco que defiende `side` (para GameState.team_goal)."""
    area = HOME_GOAL if side is TeamSide.HOME else AWAY_GOAL
    return Point2D(area.line_x, PITCH_WIDTH / 2)


def opponent_goal_center(side: TeamSide) -> Point2D:
    """Punto único del arco rival de `side` (para GameState.opponent_goal)."""
    other = TeamSide.AWAY if side is TeamSide.HOME else TeamSide.HOME
    return goal_center(other)


def default_detect_goal(ball_position: Point2D) -> Optional[TeamSide]:
    """
    Implementación de referencia de detección de gol (PLACEHOLDER, a
    confirmar con el equipo -- ver "Decisiones pendientes" del ticket).

    Regla: gol si la pelota cruzó una línea de fondo dentro del ancho
    del arco. NO contempla:
      - Qué pasa si la pelota sale por el costado (y fuera de [0, PITCH_WIDTH]).
      - Rebotes contra el palo o el travesaño.
      - Reiniciar la posición de la pelota tras el gol (eso es de
        apply_intentions / del ciclo, no de la detección en sí).

    Devuelve el lado que CONVIERTE el gol (quien lo mete), no el que lo
    recibe: si la pelota entra en el arco que defiende HOME, el gol es
    de AWAY.
    """
    if ball_position.x <= HOME_GOAL.line_x and HOME_GOAL.contains_y(ball_position.y):
        return TeamSide.AWAY
    if ball_position.x >= AWAY_GOAL.line_x and AWAY_GOAL.contains_y(ball_position.y):
        return TeamSide.HOME
    return None


# Posiciones iniciales de los titulares, asumiendo que el equipo ataca
# hacia x creciente (como HOME): los DEF cerca de x=0 (su propio arco),
# los FORWARD cerca de x=105 (el arco rival). Para AWAY se rota 180°
# (ver starter_position): así "izquierda" sigue siendo la izquierda del
# equipo mirando hacia el arco rival, no una coordenada absoluta fija.
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


def starter_position(formation_type: str, role: str, side: TeamSide) -> Point2D:
    """
    Posición inicial de un titular según su formación, rol y lado.
    """
    base = FORMATION_POSITIONS[formation_type][role]
    if side is TeamSide.HOME:
        return base
    return Point2D(PITCH_LENGTH - base.x, PITCH_WIDTH - base.y)
