# tests/unit/test_behavior_executor.py
"""
Tests de la carga y ejecución de los comportamientos.
Los comportamientos son textos con código Python, como los de Behavior.code.
Sin base de datos: el partido se arma a mano en memoria.
"""

import pytest

from src.engine.behavior_executor import load_on_tick, make_execute_behavior
from src.engine._01_to_world.data_types import (
    Point2D, Vector2D, AttributeType, ActionType, Intention
)
from src.engine.match_runner import run_tick
from src.engine._01_to_world.pitch import TeamSide
from src.engine.state import BallState, MatchPhase, MatchPlayerState, MatchState, Score


def _player(player_id, team_id, side, x, starter=True):
    return MatchPlayerState(
        player_id=player_id,
        team_id=team_id,
        side=side,
        is_starter=starter,
        role=None,
        behavior_id=1,  # por defecto todos usan el comportamiento 1
        position=Point2D(x, 10.0) if starter else None,
        attributes={a: player_id for a in AttributeType},
    )


def _state():
    """3 titulares y 1 suplente por equipo. Todos con behavior_id=1."""
    jugadores = [
        _player(101, 1, TeamSide.HOME, 10), _player(102, 1, TeamSide.HOME, 20),
        _player(103, 1, TeamSide.HOME, 30), _player(104, 1, TeamSide.HOME, 0, starter=False),
        _player(201, 2, TeamSide.AWAY, 70), _player(202, 2, TeamSide.AWAY, 80),
        _player(203, 2, TeamSide.AWAY, 90), _player(204, 2, TeamSide.AWAY, 0, starter=False),
    ]
    return MatchState(
        match_id=1,
        phase=MatchPhase.IN_PROGRESS,
        current_tick=0,
        total_ticks=240,
        score=Score(),
        ball=BallState(Point2D(52.5, 30.0), Vector2D(0.0, 0.0)),
        players={p.player_id: p for p in jugadores},
    )


# Comportamientos de prueba 
RUN_TO_OWN_POSITION = "def on_tick(api):\n    api.run_to(api.get_game_state().my_position, 0.5)"
IDLE = "def on_tick(api):\n    api.idle()"
BROKEN = "def on_tick(api):\n    raise RuntimeError('falla')"




def test_deberia_ejecutar_el_on_tick_con_el_api_del_jugador_y_devolver_su_intencion():
    state = _state()
    execute = make_execute_behavior({1: RUN_TO_OWN_POSITION})

    intention = execute(state, 201)

    # El comportamiento corre hacia SU PROPIA posición. Si el target es la
    # posición del jugador 201, el on_tick recibio el PlayerAPI de ese jugador.
    expected = Intention(ActionType.RUN_TO, target=state.players[201].position, speed_percentage=0.5)
    assert intention == expected


# --- cada comportamiento con su propio contexto, sin afectar a los demás ---
def test_deberia_cada_jugador_recibir_la_intencion_de_su_propio_comportamiento():
    state = _state()
    state.players[102].behavior_id = 2
    execute = make_execute_behavior({1: RUN_TO_OWN_POSITION, 2: IDLE})

    intention_101 = execute(state, 101)  # comportamiento 1: correr
    intention_102 = execute(state, 102)  # comportamiento 2: quedarse quieto

    assert intention_101.action == ActionType.RUN_TO
    assert intention_102.action == ActionType.IDLE


def test_deberia_la_falla_de_un_jugador_dejarlo_en_idle_y_no_afectar_a_los_demas():
    state = _state()
    state.players[101].behavior_id = 2  # solo el 101 tiene el comportamiento roto
    execute = make_execute_behavior({1: RUN_TO_OWN_POSITION, 2: BROKEN})

    # apply_intentions y detect_goal los mockeo
    run_tick(
        state,
        execute_behavior=execute,
        apply_intentions=lambda s, i: None,
        detect_goal=lambda s: None,
    )

    assert state.players[101].current_action == ActionType.IDLE    # el que falla
    assert state.players[102].current_action == ActionType.RUN_TO  


def test_deberia_fallar_al_crear_el_execute_behavior_si_el_codigo_no_define_on_tick():
    codigo_sin_on_tick = "x = 5"

    # Falla al CREAR el execute_behavior, es decir, antes de ejecutar ningún tick
    with pytest.raises(ValueError, match="on_tick"):
        make_execute_behavior({1: codigo_sin_on_tick})