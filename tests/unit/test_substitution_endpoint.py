"""
Tests de la sustitución con planificación.

Jugadores de _build_state (ver test_match_runner.py):
  - Equipo 1: titulares 100, 101, 102 | suplentes 103, 104, 105
"""

import pytest

from src.engine._01_to_world.metrics import PauseSlot, PauseType
from src.engine._02_to_match.state import (
    MatchPhase,
    PauseState,
    SubstitutionLimitError,
    match_registry,
    substitute_player,
    apply_planned_substitutions,
)
from src.engine.match_runner import _run_pause
from src.services.substitution_service import SubstitutionResult, apply_substitution
from tests.unit.test_match_runner import MATCH_ID, _build_state

EQUIPO_1 = 1


@pytest.fixture()
def partido():
    """Partido en curso, registrado en memoria y jugándose (sin pausa)."""
    state = _build_state()
    match_registry.add(state)
    yield state
    match_registry.remove(MATCH_ID)   # el registry es global: queda limpio


# ---------- servicio: en pausa se aplica, fuera de pausa se planifica ----------

def test_deberia_aplicar_el_cambio_si_hay_pausa(partido):
    partido.pause = PauseState(type=PauseType.COOLING_BREAK, number=1, ends_at=0.0)  # el partido está en pausa

    resultado = apply_substitution(MATCH_ID, EQUIPO_1, player_in_id=103, player_out_id=100)

    # Si fue durante la pausa, devuelve APPLIED
    assert resultado == SubstitutionResult.APPLIED
    # el MatchState refleja el cambio: el entrante en cancha y el saliente en el banco
    assert partido.players[103].position is not None
    assert partido.players[100].position is None

def test_deberia_dejar_el_cambio_planificado_si_no_hay_pausa(partido):
    # el partido se está jugando: state.pause es None

    resultado = apply_substitution(MATCH_ID, EQUIPO_1, player_in_id=103, player_out_id=100)

    # Como fue antes de una pausa, devuelve PLANNED 
    assert resultado == SubstitutionResult.PLANNED
    # todavía no cambió nada: el saliente sigue en cancha y el entrante en el banco
    assert partido.players[100].position is not None
    assert partido.players[103].position is None
    # solo quedó guardado el plan del equipo, como (saliente, entrante)
    assert partido.planned_substitutions == {EQUIPO_1: (100, 103)}


def test_deberia_planificar_de_nuevo_reemplazar_el_plan_anterior(partido):
    apply_substitution(MATCH_ID, EQUIPO_1, player_in_id=103, player_out_id=100)
    apply_substitution(MATCH_ID, EQUIPO_1, player_in_id=104, player_out_id=101)

    # el equipo tiene un solo plan: queda el último
    assert partido.planned_substitutions == {EQUIPO_1: (101, 104)}

# ---------- motor: el plan se aplica al empezar la pausa ----------

COOLING_BREAK = PauseSlot(number=1, tick=60, type=PauseType.COOLING_BREAK)

@pytest.mark.asyncio
async def test_deberia_aplicar_el_cambio_planificado_al_empezar_la_pausa():
    state = _build_state()
    state.planned_substitutions[EQUIPO_1] = (100, 103)   # sale el 100, entra el 103

    await _run_pause(state, COOLING_BREAK, 0)

    # el cambio queda hecho aunque la pausa ya terminó
    assert state.players[103].position is not None
    assert state.players[100].position is None
    assert state.planned_substitutions == {}   # el plan se usa una sola vez

def test_deberia_el_cambio_planificado_bloquear_otro_cambio_del_equipo_en_esa_pausa():
    state = _build_state()
    state.pause = PauseState(type=PauseType.COOLING_BREAK, number=1, ends_at=0.0)   # empezó la pausa
    state.planned_substitutions[EQUIPO_1] = (100, 103)

    apply_planned_substitutions(state)

    with pytest.raises(SubstitutionLimitError):
        # como se aplicó el plan, no se puede hacer otro cambio en la misma pausa
        substitute_player(state, EQUIPO_1, 101, 104) 

@pytest.mark.asyncio
async def test_deberia_descartar_el_cambio_planificado_que_ya_no_es_valido_y_seguir():
    state = _build_state()
    # Plan inválido: el 101 ya está en cancha, y el entrante tiene que estar en el banco.
    state.planned_substitutions[EQUIPO_1] = (100, 101)

    await _run_pause(state, COOLING_BREAK, 0)   # no debe lanzar ningún error

    assert state.planned_substitutions == {}         # el plan se descartó
    assert state.players[100].position is not None   # y no cambió nada: los dos siguen en cancha
    assert state.players[101].position is not None
    assert state.phase is MatchPhase.IN_PROGRESS     # el partido continúa