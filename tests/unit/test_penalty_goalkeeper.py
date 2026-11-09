"""
Tests del arquero de penales (src/penalty_behaviors.py) y de la atajada
(simulation._move_ball).

Un test por cada criterio de aceptación:
  CA1  assign_penalty_goalkeeper deja behavior_id None, is_goalkeeper True y un on_tick ejecutable
  CA2  cuando el arquero llega a un poste, va hacia el otro
  CA3  si la pelota pasa a menos del radio de atajada, queda quieta en el punto de contacto y no hay gol
  CA4  si la pelota pasa fuera del radio de atajada, sigue su camino sin cambios

Los tests de la atajada se escriben en función de GOALKEEPER_SAVE_RADIUS,
así siguen valiendo si se ajusta su valor.
"""

import pytest

from src.engine._01_to_world.data_types import ActionType, AttributeType, Point2D, Vector2D
from src.engine._01_to_world.metrics import GOALKEEPER_SAVE_RADIUS, TICK_DURATION_SECONDS
from src.engine._01_to_world.pitch import HOME_GOAL, TeamSide, detect_goal
from src.engine._02_to_match.state import BallState, MatchPhase, MatchPlayerState, MatchState, Score
from src.engine._03_to_builder.behavior_executor import execute_behavior
from src.engine._04_to_physics.simulation import apply_intentions
from src.penalty_behaviors import assign_penalty_goalkeeper

# ---------------------------------------------------------------------------
# Ayudas
# ---------------------------------------------------------------------------

ATTRIBUTES = {
    AttributeType.POWER: 50,
    AttributeType.AGILITY: 50,
    AttributeType.CONTROL: 50,
    AttributeType.SPEED: 50,
    AttributeType.STRENGTH: 50,
}

# Los postes del arco de HOME (x = 0), tomados de pitch.py
UPPER_POST_HOME = Point2D(HOME_GOAL.line_x, HOME_GOAL.post_max_y)
LOWER_POST_HOME = Point2D(HOME_GOAL.line_x, HOME_GOAL.post_min_y)

GOAL_CENTER_HOME = Point2D(0.0, 30.0)
R = GOALKEEPER_SAVE_RADIUS

# Un remate desde el punto del penal (x = 11) hacia el arco de HOME.
# A 30 m/s recorre 15 m en un tick: sin nadie en el medio terminaría en x = -4, adentro del arco.
SHOT_START = Point2D(11.0, 30.0)
SHOT_VELOCITY = Vector2D(-30.0, 0.0)


def _player(position=GOAL_CENTER_HOME):
    """Jugador común de HOME (no arquero), titular y en cancha, con behavior_id 1."""
    return MatchPlayerState(
        player_id=1,
        team_id=1,
        side=TeamSide.HOME,
        is_starter=True,
        role=None,
        behavior_id=1,
        position=position,
        attributes=dict(ATTRIBUTES),
    )


def _goalkeeper(position=GOAL_CENTER_HOME):
    """Jugador con el comportamiento de arquero de penales ya asignado."""
    player = _player(position)
    assign_penalty_goalkeeper(player)
    return player


def _state(player, ball_position=Point2D(52.5, 30.0), ball_velocity=Vector2D(0.0, 0.0)):
    """Partido de prueba con un solo jugador y la pelota indicada."""
    return MatchState(
        match_id=1,
        phase=MatchPhase.IN_PROGRESS,
        current_tick=0,
        total_ticks=240,
        score=Score(),
        ball=BallState(position=ball_position, velocity=ball_velocity),
        players={player.player_id: player},
    )


def _same_point(a, b):
    """True si los dos puntos son iguales (con un margen mínimo por los decimales)."""
    return (a.x, a.y) == pytest.approx((b.x, b.y))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

# CA1
def test_deberia_assign_penalty_goalkeeper_dejar_al_jugador_listo_para_atajar():
    player = _player()  # jugador común: behavior_id 1 y no es arquero

    assign_penalty_goalkeeper(player)

    assert player.behavior_id is None
    assert player.is_goalkeeper is True
    # su on_tick se puede ejecutar (si el texto fallara, este llamado haría fallar el test)
    intention = execute_behavior(_state(player), player.player_id)
    assert intention.action == ActionType.RUN_TO


# CA2
def test_deberia_el_arquero_al_llegar_a_un_poste_ir_hacia_el_otro():
    goalkeeper = _goalkeeper(position=GOAL_CENTER_HOME)
    state = _state(goalkeeper)

    # desde el centro arranca hacia el poste de "y" mayor
    assert _same_point(execute_behavior(state, 1).target, UPPER_POST_HOME)

    # llegó a ese poste: ahora va hacia el otro
    goalkeeper.position = UPPER_POST_HOME
    assert _same_point(execute_behavior(state, 1).target, LOWER_POST_HOME)

    # y al llegar al otro, vuelve
    goalkeeper.position = LOWER_POST_HOME
    assert _same_point(execute_behavior(state, 1).target, UPPER_POST_HOME)


# CA3
def test_deberia_la_pelota_que_pasa_por_el_arquero_quedar_quieta_y_no_contar_gol():
    state = _state(_goalkeeper(position=GOAL_CENTER_HOME), SHOT_START, SHOT_VELOCITY)

    apply_intentions(state, {})  # sin intenciones: el arquero no se mueve, solo avanza la pelota

    assert _same_point(state.ball.position, Point2D(R, 30.0))  # quieta, a R metros delante del arquero
    assert state.ball.velocity == Vector2D(0.0, 0.0)
    assert detect_goal(state.ball.position) is None  # quedó fuera del arco: no es gol


# CA4
def test_deberia_la_pelota_que_pasa_fuera_del_radio_seguir_su_camino():
    # El arquero está pegado al poste de arriba y el tiro pasa 0.5 m por afuera de su radio,
    # o sea por afuera de los palos: así la pelota no entra al arco y no frena por un gol
    arquero = Point2D(0.0, HOME_GOAL.post_max_y)
    start = Point2D(11.0, arquero.y + R + 0.5)
    state = _state(_goalkeeper(position=arquero), start, SHOT_VELOCITY)

    apply_intentions(state, {})

    # No la frenó el arquero: siguió su camino hasta x = -4 (detrás de la línea de fondo, por afuera
    # de los palos) y ahí rebotó, así que vuelve con la misma rapidez y el sentido de x invertido
    assert state.ball.velocity == Vector2D(-SHOT_VELOCITY.x, SHOT_VELOCITY.y)
    assert _same_point(
        state.ball.position,
        Point2D(-(start.x + SHOT_VELOCITY.x * TICK_DURATION_SECONDS), start.y),
    )
