"""
Puente entre el motor (MatchState, que no sabe nada de WebSockets ni
de JSON) y el canal en vivo de un partido (match_connections).

Separado en dos funciones a propósito:
  - build_tick_update_payload: pura, sin async, fácil de testear sin
    tocar ninguna conexión real.
  - notify: la función que efectivamente se le pasa a
    match_runner.run_match(..., notify=notify), hace el I/O.

Forma del payload: exactamente la del evento TICK_UPDATE del contrato
(WS /ws/v1/matches/{matchId}).
"""

from __future__ import annotations

from src.engine.state import MatchState
from src.realtime.match_connection_manager import match_connections


def build_tick_update_payload(state: MatchState) -> dict:
    """Arma el dict del evento TICK_UPDATE a partir del MatchState.
    Solo incluye jugadores EN CANCHA (position is not None): los
    suplentes no tienen posición que transmitir."""
    return {
        "event": "TICK_UPDATE",
        "match_id": state.match_id,
        "current_tick": state.current_tick,
        "total_ticks": state.total_ticks,
        "score": {"home": state.score.home, "away": state.score.away},
        "ball": {"x": state.ball.position.x, "y": state.ball.position.y},
        "players": [
            {
                "player_id": player.player_id,
                "team_id": player.team_id,
                "position": {"x": player.position.x, "y": player.position.y},
                "current_action": player.current_action.value,
            }
            for player in state.players.values()
            if player.position is not None
        ],
    }


async def notify(state: MatchState) -> None:
    """La función que se inyecta en run_match. Si nadie está conectado
    a este partido todavía, broadcast() no tiene a quién mandarle nada
    y no pasa nada (no es un error: el motor no debe depender de que
    haya espectadores)."""
    await match_connections.broadcast(state.match_id, build_tick_update_payload(state))
