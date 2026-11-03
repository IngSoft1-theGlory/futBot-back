"""
Tests del marcador de penales (phome y paway) en el Score:
valores por defecto y TICK_UPDATE.
"""

from src.realtime.match_broadcast import build_tick_update_payload

# Reutiliza el armado de estado de otros tests
from tests.unit.test_match_runner import _build_state  # noqa: F401


def test_deberia_un_partido_sin_penales_tener_phome_y_paway_en_none():
    state = _build_state()

    assert state.score.phome is None
    assert state.score.paway is None


def test_deberia_el_tick_update_llevar_phome_y_paway_en_none_sin_penales():
    payload = build_tick_update_payload(_build_state())

    assert payload["score"]["phome"] is None
    assert payload["score"]["paway"] is None


def test_deberia_el_tick_update_llevar_los_goles_de_penales_durante_la_tanda():
    state = _build_state()
    state.score.phome = 2
    state.score.paway = 1

    payload = build_tick_update_payload(state)

    assert payload["score"]["phome"] == 2
    assert payload["score"]["paway"] == 1


# el criterio de aceptacion "El state que se envía a FRONT incluye phome y paway con sus valores actuales" 
# queda testeado en test_deberia_devolver_200_con_el_estado_y_solo_los_6_jugadores_en_cancha 
# en el modulo test_match_state_endpoint.py 
