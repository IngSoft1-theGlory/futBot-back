"""
Tests de CoachAPI (primitivas del director técnico).

Trabajan solo con el estado en memoria, igual que test_substitute_player.py: sin base
de datos ni endpoints. La "pausa" se simula poniéndole una PauseState a state.pause.

Jugadores de _build_state (ver test_match_runner.py):
  - Equipo 1 (HOME): titulares 100, 101, 102 | suplentes 103, 104, 105
  - Equipo 2 (AWAY): titulares 200, 201, 202 | suplentes 203, 204, 205
"""

import pytest

from src.engine._01_to_world.metrics import PauseType
from src.engine._02_to_match.state import (
    InvalidSubstitutionError,
    NotInPauseError,
    PauseState,
    SubstitutionLimitError,
)
from src.engine._03_to_builder.coach_api import CoachAPI
from tests.unit.test_match_runner import _build_state

EQUIPO_1 = 1

# Códigos de comportamiento de prueba. Uno válido y otro que no carga (no define on_tick).
CODIGO_VALIDO = "def on_tick(api):\n    api.idle()"
CODIGO_INVALIDO = "x = 1"


def _coach(state, behavior_codes=None) -> CoachAPI:
    """CoachAPI del equipo 1. Por defecto puede usar el comportamiento 2 (válido)."""
    if behavior_codes is None:
        behavior_codes = {2: CODIGO_VALIDO}
    return CoachAPI(state, EQUIPO_1, behavior_codes)


def _partido_en_pausa():
    """Un partido recién armado, detenido en una pausa (substituted_team_ids arranca vacío)."""
    state = _build_state()
    state.pause = PauseState(type=PauseType.COOLING_BREAK, number=1, ends_at=0.0)
    return state


def _foto(state):
    """Foto del estado que un cambio fallido no debería alterar: quién está en cancha y quién ya cambió."""
    jugadores = {pid: (p.position, p.is_starter) for pid, p in state.players.items()}
    cambios = set(state.pause.substituted_team_ids) if state.pause else None
    return jugadores, cambios


# --- change_behavior ---

def test_deberia_change_behavior_dejar_al_jugador_con_el_comportamiento_indicado():
    state = _build_state()
    jugador = state.players[100]
    on_tick_anterior = jugador.on_tick

    _coach(state).change_behavior(100, 2)

    assert jugador.behavior_id == 2
    assert callable(jugador.on_tick)
    assert jugador.on_tick is not on_tick_anterior  # se cargó la función del código nuevo


def test_deberia_change_behavior_lanzar_error_y_conservar_el_comportamiento_si_el_codigo_no_carga():
    state = _build_state()
    jugador = state.players[100]
    behavior_id_anterior, on_tick_anterior = jugador.behavior_id, jugador.on_tick

    with pytest.raises(ValueError):  # load_on_tick lanza ValueError si el código no define on_tick
        _coach(state, {2: CODIGO_INVALIDO}).change_behavior(100, 2)

    assert jugador.behavior_id == behavior_id_anterior
    assert jugador.on_tick is on_tick_anterior


# --- substitute ---

def test_deberia_substitute_dejar_al_suplente_en_cancha_y_al_titular_en_el_banco():
    state = _partido_en_pausa()

    _coach(state).substitute(player_out_id=100, player_in_id=103)

    assert state.players[103].position is not None  # el suplente quedó en cancha
    assert state.players[100].position is None      # el titular quedó en el banco


def test_deberia_substitute_lanzar_not_in_pause_error_sin_pausa_y_no_cambiar_el_estado():
    state = _build_state()  # recién armado: state.pause es None
    antes = _foto(state)

    with pytest.raises(NotInPauseError):
        _coach(state).substitute(100, 103)

    assert _foto(state) == antes


def test_deberia_substitute_lanzar_substitution_limit_error_en_el_segundo_cambio_y_no_cambiar_el_estado():
    state = _partido_en_pausa()
    coach = _coach(state)
    coach.substitute(100, 103)  # primer cambio: OK
    antes = _foto(state)

    with pytest.raises(SubstitutionLimitError):
        coach.substitute(101, 104)

    assert _foto(state) == antes


def test_deberia_substitute_lanzar_invalid_substitution_error_con_jugadores_invalidos_y_no_cambiar_el_estado():
    state = _partido_en_pausa()
    antes = _foto(state)

    with pytest.raises(InvalidSubstitutionError):
        _coach(state).substitute(100, 101)  # el entrante ya está en cancha

    assert _foto(state) == antes


# --- lecturas ---

def test_deberia_las_lecturas_devolver_tick_pausa_titulares_y_suplentes_en_orden_de_alineacion():
    state = _build_state()
    state.current_tick = 7
    coach = _coach(state)

    assert coach.get_current_tick() == 7
    assert coach.get_pause_type() is None  # sin pausa
    assert coach.get_starters() == [100, 101, 102]
    assert coach.get_substitutes() == [103, 104, 105]

    state.pause = PauseState(type=PauseType.HALF_TIME, number=2, ends_at=0.0)
    assert coach.get_pause_type() == "HALF_TIME"
