"""
simulation: aplica las intenciones de TODOS los jugadores al MatchState.

`apply_intentions` es la pieza que `run_tick` recibe como `apply_intentions`.
Las intenciones ya fueron recolectadas sobre el mismo snapshot y se aplican
al MatchState global, mutándolo in place.

Para cada jugador reutiliza `resolve` (función pura, por jugador):
    snapshot (build_player_snapshot) -> resolve -> se escribe en el
    MatchState solo lo que esa acción puede cambiar:
        RUN_TO    -> la posición del jugador
        KICK_BALL -> la velocidad de la pelota
        IDLE      -> nada

Orden dentro de un tick: run_tick hace comportamientos -> apply_intentions
-> detect_goal. Por eso el reinicio tras un gol (la pelota al centro y TODOS
los jugadores en cancha a su posición inicial) se hace al PRINCIPIO de
apply_intentions: si se hiciera al final, detect_goal nunca vería el gol.
Un gol se detecta en el tick en que la pelota entra al arco y el reinicio
ocurre al comienzo del tick siguiente.
Al final de apply_intentions la pelota avanza según su velocidad (_move_ball).
Si en ese tramo pasa cerca de un arquero (is_goalkeeper), queda quieta en el
punto de contacto (atajada). Si cruza la línea de gol por entre los palos, queda
quieta en la línea (gol). Frena en lo primero que le toque. Como eso pasa antes de
detect_goal, una atajada no cuenta como gol.
Si no toca nada y termina fuera de la cancha (un lateral, o una línea de fondo fuera
de los palos), rebota: vuelve hacia adentro con la misma rapidez.
"""

import math
from typing import Optional

from src.engine._01_to_world.data_types import Point2D, Vector2D, ActionType, Intention
from src.engine._01_to_world.metrics import GOALKEEPER_SAVE_RADIUS, TICK_DURATION_SECONDS
from src.engine._01_to_world.pitch import (
    BALL_INITIAL_POSITION, PITCH_LENGTH, PITCH_WIDTH, detect_goal, goal_line_crossing,
)
from src.engine._02_to_match.state import MatchState
from src.engine._03_to_builder.snapshot import build_player_snapshot
from src.engine._04_to_physics.resolve import resolve


# ====================================== Aplicación de intenciones ==================================

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


# ========================================== Auxiliares =============================================

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
    """
    Avanza la pelota un tick: posicion = posicion + velocidad * duración del tick
    La pelota queda quieta en el primer punto que toca: un arquero que la ataja o la línea
    de gol. Si no toca nada y termina fuera de la cancha, rebota (ver _bounce).
    """
    start = state.ball.position
    end = Point2D(
        start.x + state.ball.velocity.x * TICK_DURATION_SECONDS,
        start.y + state.ball.velocity.y * TICK_DURATION_SECONDS,
    )

    # Lista de posiciones (Point2D) donde se frena la pelota: sea arquero o linea de gol.
    contacts = []

    for player in state.players.values():
        if player.is_goalkeeper and player.position is not None:
            contact = save_contact_point(start, end, player.position)
            if contact is not None:
                contacts.append(contact)

    # Así detect_goal ve el gol aunque el tiro termine fuera de los palos.
    # i.e: un tiro dirigido al arco que tenia end fuera de los palos, pero que cruzó la línea de gol antes.
    crossing = goal_line_crossing(start, end)
    if crossing is not None:
        contacts.append(crossing)

    # ¿Hubo un arquero o la línea de gol que frenó la pelota?: queda quieta en el primero que toca.
    # Si no hubo (lista vacía), queda quieta en el final del tick.
    if contacts:
        # frena en el primero que toca: si hay un arquero antes de la línea, es atajada
        state.ball.position = min(contacts, key=start.distance_to)
        state.ball.velocity = Vector2D(0.0, 0.0)
    else:
        # Sin contactos no hubo gol ni atajada, así que si `end` quedó fuera de la cancha
        # es por un lateral o por el fondo afuera de los palos: la pelota rebota.
        x, velocity_x = _bounce(end.x, state.ball.velocity.x, PITCH_LENGTH)
        y, velocity_y = _bounce(end.y, state.ball.velocity.y, PITCH_WIDTH)
        state.ball.position = Point2D(x, y)
        state.ball.velocity = Vector2D(velocity_x, velocity_y)


def _bounce(coordinate: float, velocity: float, limit: float) -> tuple[float, float]:
    """
    Rebote en un eje de la cancha, que va de 0 a `limit`. Devuelve (coordenada, velocidad).

    Es como un espejo en la línea: si la pelota se pasó 1 m, vuelve 1 m hacia
    adentro y la velocidad de ese eje cambia de sentido (misma rapidez).
        coordenada < 0      -> -coordenada
        coordenada > limit  -> 2 * limit - coordenada
    Una sola reflexión alcanza: la pelota avanza como máximo 15 m por tick
    (30 m/s * 0,5 s), menos que el ancho de la cancha.
    """
    if coordinate < 0:
        return -coordinate, -velocity
    if coordinate > limit:
        return 2 * limit - coordinate, -velocity
    return coordinate, velocity


# ========================================== Atajada ================================================

def save_contact_point(ball_start: Point2D, ball_end: Point2D, goalkeeper_position: Point2D) -> Optional[Point2D]:
    """
    Primer punto del tramo ball_start -> ball_end que queda a GOALKEEPER_SAVE_RADIUS
    o menos del arquero, o None si la pelota nunca pasa tan cerca

    Se revisa el tramo entero y no solo ball_end: la pelota puede recorrer hasta
    15 m en un tick y pasar de largo por delante del arquero
    """
    # la pelota ya arranca pegada al arquero: la ataja ahí mismo
    if ball_start.distance_to(goalkeeper_position) <= GOALKEEPER_SAVE_RADIUS:
        return ball_start

    path_length = ball_start.distance_to(ball_end)
    if path_length == 0:
        return None  # la pelota está quieta y lejos del arquero

    direction = ball_start.direction_to(ball_end)  # vector de largo 1, hacia donde viaja la pelota

    # Cuántos metros avanza la pelota hasta el punto de su recta más cercano al arquero, es el producto escalar entre el vector "pelota -> arquero" y la dirección
    to_goalkeeper_x = goalkeeper_position.x - ball_start.x
    to_goalkeeper_y = goalkeeper_position.y - ball_start.y
    meters_to_closest = to_goalkeeper_x * direction.x + to_goalkeeper_y * direction.y

    closest_point = _point_along_path(ball_start, direction, meters_to_closest)
    closest_distance = closest_point.distance_to(goalkeeper_position)
    if closest_distance > GOALKEEPER_SAVE_RADIUS:
        return None  # la recta de la pelota pasa lejos del arquero

    # Pitágoras desde el punto más cercano se retrocede sobre la recta hasta el borde del radio de atajada, que es donde la pelota lo toca por primera vez
    meters_back = math.sqrt(GOALKEEPER_SAVE_RADIUS ** 2 - closest_distance ** 2)
    meters_to_contact = meters_to_closest - meters_back

    # < 0: el arquero quedó atrás (la pelota se aleja) > path_length no llega en este tick
    if meters_to_contact < 0 or meters_to_contact > path_length:
        return None

    return _point_along_path(ball_start, direction, meters_to_contact)


def _point_along_path(start: Point2D, direction: Vector2D, meters: float) -> Point2D:
    """Punto al que se llega avanzando `meters` metros desde `start` en `direction` (de largo 1)"""
    return Point2D(start.x + direction.x * meters, start.y + direction.y * meters)