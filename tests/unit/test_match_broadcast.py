"""
Tests de match_broadcast: payloads de pausa (funciones puras) y
notify / notify_pause (I/O, usando el match_connections real pero con una conexión fake).
"""

import pytest

from src.engine._02_to_match.state import TeamMatchSetup, build_initial_state
from src.engine._01_to_world.pitch import TeamSide
from src.engine._01_to_world.data_types import AttributeType
from src.engine._01_to_world.metrics import PauseType
from src.schemas.lineup_config import LineupConfig, StartingPlayer, SubstitutePlayer
from src.realtime.match_broadcast import build_tick_update_payload, notify, build_pause_started_payload, build_pause_finished_payload, notify_pause
from src.realtime.match_connection_manager import match_connections


ATTRIBUTES = {
    AttributeType.POWER: 80,
    AttributeType.AGILITY: 50,
    AttributeType.CONTROL: 60,
    AttributeType.SPEED: 80,
    AttributeType.STRENGTH: 50,
}


def _setup(team_id: int, side: TeamSide, base_player_id: int) -> TeamMatchSetup:
    roles = ["DEF_LEFT", "DEF_RIGHT", "FORWARD"]
    lineup = LineupConfig(
        formation_type="2-1",
        starting_players=[
            StartingPlayer(player_id=base_player_id + i, role=role, behavior_id=1)
            for i, role in enumerate(roles)
        ],
        substitute_players=[
            SubstitutePlayer(player_id=base_player_id + 3 + i, behavior_id=1)
            for i in range(3)
        ],
    )
    # los mismos atributos para los 6 jugadores del equipo
    attributes = {base_player_id + i: dict(ATTRIBUTES) for i in range(6)}
    return TeamMatchSetup(team_id=team_id, side=side, lineup=lineup, attributes=attributes)


def _build_state(match_id: int = 1):
    home = _setup(team_id=1, side=TeamSide.HOME, base_player_id=100)
    away = _setup(team_id=2, side=TeamSide.AWAY, base_player_id=200)
    return build_initial_state(match_id, total_ticks=240, home=home, away=away)


class _FakeWebSocket:
    def __init__(self):
        # Guarda los mensajes enviados para poder verificarlos sin usar una conexión real.
        self.recibidos: list[dict] = []

    async def send_json(self, data: dict) -> None:
        self.recibidos.append(data)


@pytest.mark.asyncio
async def test_deberia_notify_transmitir_por_match_connections():
    """Usa el singleton real match_connections -- se limpia al final
    para no dejar estado colgado entre tests."""
    state = _build_state(match_id=999)
    ws = _FakeWebSocket()
    match_connections.register(999, ws)

    try:
        await notify(state)
    finally:
        match_connections.unregister(999, ws)

    assert len(ws.recibidos) == 1
    assert ws.recibidos[0]["event"] == "TICK_UPDATE"
    assert ws.recibidos[0]["match_id"] == 999


@pytest.mark.parametrize("tipo", [PauseType.COOLING_BREAK, PauseType.HALF_TIME])
def test_deberia_pause_started_payload_llevar_el_tipo_recibido(tipo):
    """ verifica que el diccionario con informacion (payload) de PAUSE_STARTED 
    tenga el tipo y campos correctos """
    payload = build_pause_started_payload(12, tipo, 20, 300)
    assert payload == {
        "event": "PAUSE_STARTED", "match_id": 12,
        "type": tipo.value, "duration_seconds": 20, "current_tick": 300,
    }


@pytest.mark.parametrize("tipo", [PauseType.COOLING_BREAK, PauseType.HALF_TIME])
def test_deberia_pause_finished_payload_llevar_el_tipo_recibido(tipo):
    """ verifica que el diccionario con informacion (payload) de PAUSE_FINISHED 
    tenga el tipo y campos correctos """
    payload = build_pause_finished_payload(12, tipo)
    assert payload == {"event": "PAUSE_FINISHED", "match_id": 12, "type": tipo.value} 


@pytest.mark.asyncio
# El payload esperado cambia según si se informa el inicio o la finalización de la pausa
@pytest.mark.parametrize("started, esperado", [ 
    (True, {"event": "PAUSE_STARTED", "match_id": 999, "type": "HALF_TIME",
            "duration_seconds": 20, "current_tick": 120}),
    (False, {"event": "PAUSE_FINISHED", "match_id": 999, "type": "HALF_TIME"}),
])

async def test_deberia_notify_pause_transmitir_el_evento_a_los_conectados(started, esperado):
    state = _build_state(match_id=999)
    state.current_tick = 120
    ws = _FakeWebSocket()
    # Se registra una conexión falsa para comprobar que notify envía el payload al partido correcto.
    match_connections.register(999, ws) 

    try: # notifi_pause envia los eventos a los clientes conectados al partido
        await notify_pause(state, PauseType.HALF_TIME, 20, started)
    finally:
        # Se elimina la conexión aunque el envío o la aserción fallen,
        # para que el singleton no conserve estado entre tests.
        match_connections.unregister(999, ws)

    assert ws.recibidos == [esperado] # se verifica si es el evento esperado