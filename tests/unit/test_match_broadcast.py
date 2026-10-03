"""
Tests de match_broadcast: build_tick_update_payload (pura) y notify
(I/O, usando el match_connections real pero con una conexión fake).
"""

import pytest

from src.engine.intentions import ActionType
from src.engine.pitch import TeamSide
from src.engine.state import LineupPlayer, TeamMatchSetup, build_initial_state
from src.realtime.match_broadcast import build_tick_update_payload, notify
from src.realtime.match_connection_manager import match_connections


def _setup(team_id: int, side: TeamSide, base_player_id: int) -> TeamMatchSetup:
    roles = ["DEF_LEFT", "DEF_RIGHT", "FORWARD"]
    starters = [
        LineupPlayer(player_id=base_player_id + i, is_starter=True, role=role, behavior_id=1)
        for i, role in enumerate(roles)
    ]
    substitutes = [
        LineupPlayer(player_id=base_player_id + 3 + i, is_starter=False, role=None, behavior_id=1)
        for i in range(3)
    ]
    return TeamMatchSetup(team_id=team_id, formation_type="2-1", side=side, players=starters + substitutes)


def _build_state(match_id: int = 1):
    home = _setup(team_id=1, side=TeamSide.HOME, base_player_id=100)
    away = _setup(team_id=2, side=TeamSide.AWAY, base_player_id=200)
    return build_initial_state(match_id, total_ticks=240, home=home, away=away)


def test_deberia_el_payload_traer_los_campos_del_contrato():
    state = _build_state()

    payload = build_tick_update_payload(state)

    assert payload["event"] == "TICK_UPDATE"
    assert payload["match_id"] == state.match_id
    assert payload["current_tick"] == state.current_tick
    assert payload["total_ticks"] == state.total_ticks
    assert payload["score"] == {"home": 0, "away": 0}
    assert payload["ball"] == {"x": state.ball.position.x, "y": state.ball.position.y}


def test_deberia_el_payload_incluir_solo_a_los_titulares():
    state = _build_state()

    payload = build_tick_update_payload(state)

    player_ids = {p["player_id"] for p in payload["players"]}
    assert player_ids == set(state.on_pitch_player_ids())
    assert len(payload["players"]) == 6  # 3 titulares x 2 equipos


def test_deberia_el_payload_mandar_current_action_como_string_del_contrato():
    state = _build_state()
    state.players[101].current_action = ActionType.KICK_BALL

    payload = build_tick_update_payload(state)

    jugador_101 = next(p for p in payload["players"] if p["player_id"] == 101)
    assert jugador_101["current_action"] == "kick_ball"


class _FakeWebSocket:
    def __init__(self):
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
