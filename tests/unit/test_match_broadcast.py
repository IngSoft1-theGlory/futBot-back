"""
Tests de match_broadcast: notify
(I/O, usando el match_connections real pero con una conexión fake).
"""

import pytest

from src.engine._01_to_world.data_types import AttributeType
from src.engine.pitch import TeamSide
from src.engine.state import TeamMatchSetup, build_initial_state
from src.schemas.lineup_config import LineupConfig, StartingPlayer, SubstitutePlayer
from src.realtime.match_broadcast import build_tick_update_payload, notify
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
