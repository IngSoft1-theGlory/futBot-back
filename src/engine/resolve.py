"""
resolve: función pura que aplica una Intention a un GameState.
"""

from dataclasses import replace

from src.engine.constants import (
    MAX_ATTRIBUTE_VALUE,
    MAX_RUN_SPEED_METERS_PER_SECOND,
    kick_speed,
    reach_distance,
)
from src.engine.game_types import AttributeType, GameState
from src.engine.geometry_types import Point2D, Vector2D
from src.engine.intentions import ActionType, Intention
from src.engine._01_to_world.pitch import PITCH_LENGTH, PITCH_WIDTH
from src.engine.timing import TICK_DURATION_SECONDS


def resolve(state: GameState, intention: Intention, attributes: dict[AttributeType, int]) -> GameState:
    """
    Devuelve el GameState resultante de aplicar `intention`.
    `attributes` son los atributos del jugador (RUN_TO usa su SPEED).

    Implementadas: IDLE, RUN_TO y KICK_BALL (usa POWER y CONTROL del jugador).
    Una acción desconocida falla fuerte en vez de ignorarse en silencio.
    """
    if intention.action == ActionType.IDLE:
        return state

    if intention.action == ActionType.RUN_TO:
        max_distance = max_run_distance_per_tick(attributes[AttributeType.SPEED], intention.speed_percentage)
        new_position = move_towards(state.my_position, intention.target, max_distance)
        # replace() crea un GameState nuevo, igual al anterior salvo my_position
        return replace(state, my_position=new_position)

    if intention.action == ActionType.KICK_BALL:
        return _resolve_kick_ball(state, intention, attributes)

    raise NotImplementedError(f"Acción no implementada: {intention.action}")


def _resolve_kick_ball(state: GameState, intention: Intention, attributes: dict[AttributeType, int]) -> GameState:
    """
    Patada: solo cambia ball_velocity, y solo si la pelota está al alcance
    (distancia <= reach_distance(CONTROL), borde inclusive).
    Fuera de alcance devuelve el MISMO estado (no se pisa la velocidad de la pelota).
    El movimiento de la pelota por tick (posición += velocidad) no es de acá.
    """
    reach = reach_distance(attributes[AttributeType.CONTROL])
    if state.my_position.distance_to(state.ball_position) > reach:
        return state

    speed = kick_speed(attributes[AttributeType.POWER], intention.power_percentage)
    direction = intention.direction.normalize()
    new_velocity = Vector2D(direction.x * speed, direction.y * speed)
    return replace(state, ball_velocity=new_velocity)


def max_run_distance_per_tick(speed_attribute: int, speed_percentage: float) -> float:
    """
    distancia maxima (en metros) que puede correr un jugador en un tick

        velocidad máxima (m/s) = MAX_RUN_SPEED * SPEED / MAX_ATTRIBUTE_VALUE
        distancia por tick     = velocidad maxima * speed_percentage * duracion del tick

    ejemplo: SPEED 100 a fondo (1.0) -> 8 m/s * 0.5 s = 4 metros por tick
    """
    max_speed = MAX_RUN_SPEED_METERS_PER_SECOND * speed_attribute / MAX_ATTRIBUTE_VALUE
    return max_speed * speed_percentage * TICK_DURATION_SECONDS


def move_towards(start: Point2D, target: Point2D, max_distance: float) -> Point2D:
    """
    Avanza en linea recta desde `start` hacia `target`, como maximo
    `max_distance` metros, y nunca termina fuera de la cancha.
    """
    distance = start.distance_to(target)

    if distance <= max_distance:
        ## Llega en este tick: queda exactamente en target (sin pasarse), también cubre target == start (distancia 0): no se mueve y nunca se calcula una direccion con el vector cero
        new_position = target
    else:
        ## no llega: avanza max_distance en la dirección de target
        direction = start.direction_to(target)  # vector de largo 1
        new_position = Point2D(
            start.x + direction.x * max_distance,
            start.y + direction.y * max_distance,
        )

    ## si target estaba fuera de la cancha, el jugador queda en el borde
    return clamp_to_pitch(new_position)


def clamp_to_pitch(position: Point2D) -> Point2D:
    ## devuelve `position` recortada a los limites de la cancha
    x = min(max(position.x, 0.0), PITCH_LENGTH)
    y = min(max(position.y, 0.0), PITCH_WIDTH)
    return Point2D(x, y)
