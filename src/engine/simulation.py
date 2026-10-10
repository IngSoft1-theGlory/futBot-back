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
-> detect_goal. Por eso el reinicio tras un gol (la pelota al centro y TODOS
los jugadores en cancha a su posición inicial) se hace al PRINCIPIO de
apply_intentions: si se hiciera al final, detect_goal nunca vería el gol.
Un gol entonces se detecta en el tick en que la pelota entra al arco y el
reinicio ocurre al comienzo del tick siguiente.
Al final de apply_intentions la pelota avanza según su velocidad (_move_ball).

Fuera de alcance:
  - Qué pasa si la pelota sale por un lateral o por el fondo fuera del arco
    (hoy sigue de largo: no hay rebote ni saque).
  - Dos jugadores pateando en el mismo tick. POLÍTICA PROVISORIA: se
    aplican en orden de player_id ascendente y gana la última patada
    (es determinista, pero no es una decisión de diseño definitiva).
"""
from src.engine._01_to_world.data_types import Point2D, Vector2D, ActionType, Intention
from src.engine.pitch import BALL_INITIAL_POSITION, detect_goal
from src.engine.resolve import resolve
from src.engine.snapshot import build_player_snapshot
from src.engine.state import MatchState
from src.engine.timing import TICK_DURATION_SECONDS


def apply_intentions(state: MatchState, intentions: dict[int, Intention]) -> None:
    """Aplica las intenciones de un tick al `state` global (lo muta in place)."""
    _reset_after_goal(state)

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
            # de alcance: en ese caso no se toca la pelota.
            state.ball.velocity = resolved.ball_velocity

    # Con las patadas ya aplicadas, la pelota avanza según su velocidad.
    # Corre ANTES de detect_goal (run_tick), así que el gol se ve en este mismo tick.
    _move_ball(state)


def _reset_after_goal(state: MatchState) -> None:
    """
    Si la pelota quedó dentro de un arco (gol del tick anterior): la pelota vuelve
    al centro, quieta, y cada jugador en cancha vuelve a su posición inicial.
    Los suplentes (position=None) siguen en el banco.
    """
    if detect_goal(state.ball.position) is None:
        return

    state.ball.position = BALL_INITIAL_POSITION
    state.ball.velocity = Vector2D(0.0, 0.0)

    for player in state.players.values():
        if player.position is not None and player.initial_position is not None:
            player.position = player.initial_position


def _move_ball(state: MatchState) -> None:
    """Avanza la pelota un tick: posición += velocidad * duración del tick."""
    state.ball.position = Point2D(
        state.ball.position.x + state.ball.velocity.x * TICK_DURATION_SECONDS,
        state.ball.position.y + state.ball.velocity.y * TICK_DURATION_SECONDS,
    )
