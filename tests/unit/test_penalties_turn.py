"""
Tests de la preparación de un turno de la tanda de penales (prepare_turn).
"""

import pytest

from src.engine._01_to_world.data_types import ActionType
from src.engine._01_to_world.pitch import PENALTY_BALL_GAP, PENALTY_DISTANCE, TeamSide, goal_center
from src.engine._02_to_match.state import swap_sides
from src.engine._03_to_builder.behavior_executor import execute_behavior
from src.engine.penalties import prepare_shootout, prepare_turn

# Reutiliza el estado de prueba del motor: equipo 1 (host, HOME) con titulares 100-102
# y equipo 2 (AWAY) con titulares 200-202
from tests.unit.test_match_runner import _build_state

# Arco de los penales: el izquierdo (x=0). Se arma acá a propósito y no se toma del código que se prueba
ARCO_IZQUIERDO = goal_center(TeamSide.HOME)

def _estado_con_tanda():
    """Estado con la tanda preparada y órdenes fijos (sin azar): el jugador i-ésimo patea y ataja en la ronda i."""
    state = _build_state()
    swap_sides(state)  # como en un partido real: los penales llegan después del Half-Time
    prepare_shootout(state)
    state.penalty_shootout.kicker_order = {1: [100, 101, 102], 2: [200, 201, 202]}
    state.penalty_shootout.keeper_order = {1: [100, 101, 102], 2: [200, 201, 202]}
    return state


def test_deberia_el_arquero_quedar_en_el_arco_izquierdo():
    state = _estado_con_tanda()

    prepare_turn(state, kicker_team_id=1, keeper_team_id=2, round_index=0)  # patea el equipo 1, ataja el equipo 2

    arquero = state.players[200]
    assert arquero.position == ARCO_IZQUIERDO


def test_deberia_el_pateador_quedar_a_distancia_de_penal_y_la_pelota_cerca():
    state = _estado_con_tanda()

    prepare_turn(state, kicker_team_id=1, keeper_team_id=2, round_index=0)

    arco = ARCO_IZQUIERDO
    pateador = state.players[100]
    assert pateador.position.distance_to(arco) == pytest.approx(PENALTY_DISTANCE)
    # la pelota está a PENALTY_BALL_GAP del pateador, del lado del arco, y quieta
    assert state.ball.position.distance_to(pateador.position) == pytest.approx(PENALTY_BALL_GAP)
    assert state.ball.position.distance_to(arco) < pateador.position.distance_to(arco)
    assert (state.ball.velocity.x, state.ball.velocity.y) == (0.0, 0.0)


def test_deberia_cada_jugador_tener_su_comportamiento():
    state = _estado_con_tanda()

    prepare_turn(state, kicker_team_id=1, keeper_team_id=2, round_index=0)

    # Se ejecuta el on_tick de cada uno: el arquero corre hacia un poste y el pateador, con la
    # pelota quieta y a su alcance, patea
    assert execute_behavior(state, 200).action == ActionType.RUN_TO
    assert execute_behavior(state, 100).action == ActionType.KICK_BALL


def test_deberia_quedar_solo_con_el_comportamiento_arquero_quien_pateo_en_el_turno_anterior():
    state = _estado_con_tanda()

    # Turno 1: el jugador 100 patea y el 200 ataja
    prepare_turn(state, kicker_team_id=1, keeper_team_id=2, round_index=0)
    on_tick_de_pateador = state.players[100].on_tick

    # Turno 2: ahora patea el 200 y ataja el 100, que pateó en el turno anterior
    prepare_turn(state, kicker_team_id=2, keeper_team_id=1, round_index=0)

    ex_pateador = state.players[100]
    assert ex_pateador.on_tick is not on_tick_de_pateador  # se retiró el comportamiento anterior
    assert ex_pateador.is_goalkeeper is True
    # si conservara el de pateador, con la pelota lejos haría idle: ataja de verdad si corre hacia un poste
    assert execute_behavior(state, 100).action == ActionType.RUN_TO
    # y el que ataja antes y patea ahora, queda solo como pateador
    assert state.players[200].is_goalkeeper is False
    assert execute_behavior(state, 200).action == ActionType.KICK_BALL