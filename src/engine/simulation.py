"""
apply_intentions: la pieza que `run_tick` recibe como `apply_intentions`.

Toma las intenciones de TODOS los jugadores (ya recolectadas sobre el
mismo snapshot) y las aplica al MatchState global, mutándolo in place.

Para cada jugador reutiliza `resolve` (función pura, por jugador):
    snapshot (build_player_snapshot) -> resolve -> se escribe en el
    MatchState solo lo que esa acción puede cambiar:
        RUN_TO    -> la posición del jugador
        KICK_BALL -> la velocidad de la pelota
        IDLE      -> nada

Orden dentro de un tick: run_tick hace  comportamientos -> apply_intentions
-> detect_goal. Por eso la pelota se reinicia al PRINCIPIO de
apply_intentions: si se reiniciara al final, detect_goal nunca vería el gol.
Un gol entonces se detecta en el tick en que la pelota entra al arco y la
pelota vuelve al centro al comienzo del tick siguiente.

Fuera de alcance (otros tickets, se dejan documentados acá):
  - Mover la pelota según su velocidad en cada tick (posición += velocidad * dt).
  - Rebotes, cooldown de patada (AGILITY), STRENGTH.
  - Dos jugadores pateando en el mismo tick. POLÍTICA PROVISORIA: se
    aplican en orden de player_id ascendente y gana la última patada
    (es determinista, pero no es una decisión de diseño definitiva).
"""

from src.engine.geometry_types import Vector2D
from src.engine.intentions import ActionType, Intention
from src.engine.pitch import BALL_INITIAL_POSITION, default_detect_goal
from src.engine.resolve import resolve
from src.engine.snapshot import build_player_snapshot
from src.engine.state import MatchState


def apply_intentions(state: MatchState, intentions: dict[int, Intention]) -> None:
    """Aplica las intenciones de un tick al `state` global (lo muta in place)."""
    _reset_ball_if_goal(state)

    # Todos los snapshots salen del estado ANTERIOR a aplicar nada: ningún
    # jugador ve el movimiento de otro del mismo tick.
    snapshots = {}
    for player_id in intentions:
        # Un suplente (position=None) no puede actuar: no se lo aplica.
        if state.players[player_id].position is not None:
            snapshots[player_id] = build_player_snapshot(state, player_id)

    # Orden fijo por player_id: el resultado no depende del orden del dict.
    for player_id in sorted(snapshots):
        game_state, attributes = snapshots[player_id]
        intention = intentions[player_id]
        resolved = resolve(game_state, intention, attributes)

        if intention.action == ActionType.RUN_TO:
            state.players[player_id].position = resolved.my_position
        elif intention.action == ActionType.KICK_BALL and resolved is not game_state:
            # `resolve` devuelve el MISMO objeto cuando la pelota estaba fuera
            # de alcance: en ese caso no se toca la pelota (así no pisa la
            # patada de otro jugador con la velocidad vieja).
            state.ball.velocity = resolved.ball_velocity


def _reset_ball_if_goal(state: MatchState) -> None:
    """Si la pelota quedó dentro de un arco (gol del tick anterior), vuelve al centro, quieta."""
    if default_detect_goal(state.ball.position) is not None:
        state.ball.position = BALL_INITIAL_POSITION
        state.ball.velocity = Vector2D(0.0, 0.0)
