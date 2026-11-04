"""
Tests de la preparación de la tanda de penales y de sus avisos por WebSocket.
"""

import pytest

from src.engine.penalties import prepare_shootout
from src.realtime.match_broadcast import (
    build_penalties_finished_payload,
    build_penalties_started_payload,
    notify_penalties,
)
from src.realtime.match_connection_manager import match_connections

# Reutiliza el estado de prueba y los fakes de los tests del motor y del broadcast
from tests.unit.test_match_broadcast import _FakeWebSocket 
from tests.unit.test_match_runner import _build_state  

# Titulares de cada equipo en _build_state (los suplentes son 103-105 y 203-205)
TITULARES = {1: [100, 101, 102], 2: [200, 201, 202]}


# --- Preparación de la tanda ----------------------------------------------------

def test_deberia_no_volver_a_sortear_si_la_tanda_ya_esta_preparada():
    state = _build_state()

    # Primer pedido de preparación: sortea el orden de pateadores y arqueros.
    prepare_shootout(state)

    # Se reemplaza el orden por uno inventado, que ningún sorteo puede generar (el jugador 999
    # no existe). Si la función sortea de nuevo, lo pisa y el assert de abajo falla.
    state.penalty_shootout.kicker_order[1] = [999]

    # Segundo pedido de preparación: no debería sortear de nuevo, sino dejar el orden que ya estaba.
    prepare_shootout(state)

    # Verificamos que el orden de pateadores del equipo 1 sigue siendo el inventado, lo que indica 
    # que no se sorteó de nuevo.
    assert state.penalty_shootout.kicker_order[1] == [999]


def test_deberia_el_orden_de_pateadores_y_arqueros_tener_solo_a_los_titulares_sin_repetidos_ni_faltantes():
    state = _build_state()

    prepare_shootout(state)

    tanda = state.penalty_shootout

    for team_id, titulares in TITULARES.items():
        # sorted solo sirve para comparar: el sorteo deja los jugadores en cualquier orden
        # Ejemplo: Tras sorteo [101, 102, 100], para comparar con los titulares [100, 101, 102]
        # se ordenan con sorted().
        assert sorted(tanda.kicker_order[team_id]) == titulares
        assert sorted(tanda.keeper_order[team_id]) == titulares


def test_deberia_inicializar_el_marcador_de_penales_en_0_0():
    state = _build_state()

    prepare_shootout(state)

    assert (state.score.phome, state.score.paway) == (0, 0)


def test_deberia_dejar_la_tanda_preparada_con_el_orden_de_ambos_equipos():
    state = _build_state()

    prepare_shootout(state)

    tanda = state.penalty_shootout
    assert tanda.prepared is True

    # Tomo solo las claves de los dicts, para verificar que ambos equipos tienen su orden de pateadores 
    # y arqueros.
    assert set(tanda.kicker_order) == {1, 2}
    assert set(tanda.keeper_order) == {1, 2}


# --- Avisos por WebSocket -------------------------------------------------------

def test_deberia_el_aviso_de_inicio_llevar_penalties_started_y_el_match_id():
    assert build_penalties_started_payload(12) == {"event": "PENALTIES_STARTED", "match_id": 12}


def test_deberia_el_aviso_de_fin_llevar_penalties_finished_y_el_match_id():
    assert build_penalties_finished_payload(12) == {"event": "PENALTIES_FINISHED", "match_id": 12}


@pytest.mark.asyncio
async def test_deberia_notify_penalties_transmitir_el_inicio_y_el_fin_a_los_conectados():
    state = _build_state()
    ws = _FakeWebSocket()
    # Se registra una conexión falsa para comprobar que los avisos llegan al partido correcto
    match_connections.register(state.match_id, ws)

    try:
        await notify_penalties(state, True)
        await notify_penalties(state, False)
    finally:
        # Se elimina la conexión aunque algo falle, para no dejar estado entre tests
        match_connections.unregister(state.match_id, ws)

    assert ws.recibidos == [
        {"event": "PENALTIES_STARTED", "match_id": state.match_id},
        {"event": "PENALTIES_FINISHED", "match_id": state.match_id},
    ]