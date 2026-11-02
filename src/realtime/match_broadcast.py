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

from src.engine._01_to_world.metrics import PauseType
from src.engine._02_to_match.state import MatchState
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
        "score": {"home": state.score.home, "away": state.score.away, 
                  "phome": state.score.phome, "paway": state.score.paway},
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


def build_pause_started_payload(
        match_id: int, 
        pause_type: PauseType, 
        duration_seconds: float, 
        current_tick: int
) -> dict:
    """ Arma el dict del evento PAUSE_STARTED (Cooling Break o Half-Time) """
    return {
        "event": "PAUSE_STARTED",
        "match_id": match_id,
        "type": pause_type.value,
        "duration_seconds": duration_seconds,
        "current_tick": current_tick,
    }


def build_pause_finished_payload(match_id: int, pause_type: PauseType) -> dict:
    """ Arma el dict del evento PAUSE_FINISHED (Cooling Break o Half-Time) """
    return {
        "event": "PAUSE_FINISHED",
        "match_id": match_id,
        "type": pause_type.value,
    }


async def notify_pause(
        state: MatchState, 
        pause_type: PauseType, 
        duration_seconds: float, 
        started: bool
) -> None:
    """ Notifica a los clientes conectados al partido que empezó o 
    terminó la pausa (en Cooling Break o Half-Time) """
   
    # si la pausa empezo, se prepara la info (payload) para  los clientes,
    # y si no se cierra la pausa, se prepara el payload para avisar que terminó la pausa.
    if started:
        payload = build_pause_started_payload(
            state.match_id, pause_type, duration_seconds, state.current_tick)
    else:
        payload = build_pause_finished_payload(state.match_id, pause_type)
  
    # se transmite el info (payload) a todos los clientes conectados 
    # al partido, avisando que la pausa empezó o terminó.
    await match_connections.broadcast(state.match_id, payload)