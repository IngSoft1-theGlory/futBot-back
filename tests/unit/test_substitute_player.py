"""
Tests de la función substitute_player.

Trabajan solo con el estado en memoria: sin base de datos, sin endpoint y sin
correr el partido entero. La "pausa" se simula poniéndole una PauseState a state.pause.

Jugadores de _build_state (ver test_match_runner.py):
  - Equipo 1 (HOME): titulares 100 (DEF_LEFT), 101, 102 | suplentes 103, 104, 105
  - Equipo 2 (AWAY): titulares 200, 201, 202            | suplentes 203, 204, 205
"""

from unittest.mock import Mock # Utilizado para reemplazar funciones que no nos interesan en estos tests.

import pytest

from src.engine._01_to_world.data_types import ActionType, AttributeType
from src.engine._01_to_world.metrics import PauseType
from src.engine._03_to_builder.behavior_executor import execute_behavior
from src.engine._02_to_match.state import (
    InvalidSubstitutionError,
    NotInPauseError,
    PauseState,
    SubstitutionLimitError,
    substitute_player,
)
from src.engine.match_runner import run_tick
from tests.unit.test_match_runner import _build_state

EQUIPO_1 = 1
EQUIPO_2 = 2


def _nueva_pausa() -> PauseState:
    """Una pausa nueva: igual que en el motor, substituted_team_ids arranca vacío."""
    return PauseState(type=PauseType.COOLING_BREAK, number=1, ends_at=0.0)


def _partido_en_pausa():
    """Un partido recién armado, detenido en una pausa."""
    state = _build_state()
    state.pause = _nueva_pausa()
    return state

def test_deberia_el_entrante_ocupar_el_lugar_del_saliente_y_el_saliente_ir_al_banco():
    state = _partido_en_pausa()
    saliente, entrante = state.players[100], state.players[103]

    # Les damos atributos y behavior_id distintos a cada uno: si la función los
    # intercambiara por error, el test lo detectaría (con valores iguales no).
    saliente.attributes[AttributeType.POWER] = 90
    entrante.attributes[AttributeType.POWER] = 10
    saliente.behavior_id, entrante.behavior_id = 7, 8

    # Guardamos lo que tenía el saliente ANTES del cambio, para compararlo después.
    posicion, rol, posicion_inicial = saliente.position, saliente.role, saliente.initial_position
    saliente.current_action = ActionType.RUN_TO  # venía corriendo en el último tick

    substitute_player(state, EQUIPO_1, player_out_id=100, player_in_id=103)

    # El entrante hereda la posición, el rol y la posición inicial del saliente.
    assert entrante.position == posicion
    assert entrante.role == rol
    assert entrante.initial_position == posicion_inicial
    assert entrante.is_starter is True

    # El saliente queda en el banco: sin posición ni rol, y quieto.
    assert saliente.position is None
    assert saliente.role is None
    assert saliente.initial_position is None
    assert saliente.is_starter is False
    assert saliente.current_action == ActionType.IDLE

    # Los atributos y el behavior_id de cada uno no cambian.
    assert saliente.attributes[AttributeType.POWER] == 90 and saliente.behavior_id == 7
    assert entrante.attributes[AttributeType.POWER] == 10 and entrante.behavior_id == 8

def test_deberia_el_siguiente_tick_ejecutar_el_comportamiento_del_entrante_y_no_el_del_saliente():
    state = _partido_en_pausa()

    # Cada jugador guarda su propia on_tick (ver assign_behavior). Acá son Mocks que
    # cuentan cuántas veces los ejecutan. El executor real las llama solo para los
    # jugadores en cancha, porque run_tick recorre state.on_pitch_player_ids().
    for jugador in state.players.values():
        jugador.on_tick = Mock()

    substitute_player(state, EQUIPO_1, player_out_id=100, player_in_id=103)

    # Se juega un tick: solo se usan mocks para la física y el gol.
    run_tick(
        state,
        execute_behavior=execute_behavior,   # detección de interés
        apply_intentions=Mock(),             # fisica falsa
        detect_goal=Mock(return_value=None), # detección de gol falsa, retornamos que no hubo gol.
    )

    # Verificamos únicamente que se haya llamado al on_tick del entrante y no al del saliente.
    # assert_called_onde() assert_not_called() son métodos de los Mocks que cuentan cuántas veces 
    # fueron llamados.
    state.players[103].on_tick.assert_called_once()  # el entrante juega con su comportamiento
    state.players[100].on_tick.assert_not_called()   # el saliente ya no juega

def test_deberia_lanzar_not_in_pause_error_si_no_hay_pausa():
    state = _build_state()  # recién armado: state.pause es None

    with pytest.raises(NotInPauseError):
        substitute_player(state, EQUIPO_1, player_out_id=100, player_in_id=103)

@pytest.mark.parametrize(
    "player_out_id, player_in_id",
    [
        (100, 101),  # el entrante ya está en cancha
        (103, 104),  # el saliente está en el banco
        (200, 103),  # el saliente es de otro equipo (el 200 juega en el equipo 2)
    ],
)
def test_deberia_lanzar_invalid_substitution_error_con_jugadores_invalidos(player_out_id, player_in_id):
    state = _partido_en_pausa()

    with pytest.raises(InvalidSubstitutionError):
        substitute_player(state, EQUIPO_1, player_out_id, player_in_id)

def test_deberia_lanzar_substitution_limit_error_en_el_segundo_cambio_del_equipo_en_la_misma_pausa():
    state = _partido_en_pausa()
    substitute_player(state, EQUIPO_1, player_out_id=100, player_in_id=103)  # primer cambio: OK

    # Segundo cambio del equipo 1 en la misma pausa (con jugadores válidos): no se permite.
    with pytest.raises(SubstitutionLimitError):
        substitute_player(state, EQUIPO_1, player_out_id=101, player_in_id=104)

def test_deberia_poder_cambiar_el_otro_equipo_despues_del_cambio_de_un_equipo():
    state = _partido_en_pausa()
    substitute_player(state, EQUIPO_1, player_out_id=100, player_in_id=103)

    # El límite es por equipo: el equipo 2 todavía no cambió, no debe fallar.
    substitute_player(state, EQUIPO_2, player_out_id=200, player_in_id=203)

    assert state.players[203].position is not None  # el entrante del equipo 2 quedó en cancha
    assert state.players[200].position is None      # y su saliente en el banco

def test_deberia_poder_volver_a_cambiar_el_equipo_en_la_pausa_siguiente():
    state = _partido_en_pausa()
    substitute_player(state, EQUIPO_1, player_out_id=100, player_in_id=103)

    # Termina la pausa y empieza otra. El motor hace state.pause = None y después crea
    # una PauseState nueva (ver _run_pause), con substituted_team_ids vacío: simulamos eso.
    state.pause = None
    state.pause = _nueva_pausa()

    # El equipo 1 ya cambió en la pausa anterior, pero en esta puede volver a hacerlo.
    substitute_player(state, EQUIPO_1, player_out_id=101, player_in_id=104)

    assert state.players[104].position is not None
    assert state.players[101].position is None
