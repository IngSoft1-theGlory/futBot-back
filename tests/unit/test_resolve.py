"""
Tests del resolve: aplica una Intention a un GameState.
IDLE, RUN_TO y KICK_BALL.
"""

from dataclasses import replace

import pytest

from src.engine.constants import (
    MAX_ATTRIBUTE_VALUE,
    MAX_KICK_SPEED_METERS_PER_SECOND,
    MAX_RUN_SPEED_METERS_PER_SECOND,
    reach_distance,
)
from src.engine.game_types import AttributeType, GameState
from src.engine.geometry_types import Point2D, Vector2D
from src.engine.intentions import ActionType, Intention
from src.engine.pitch import PITCH_LENGTH, PITCH_WIDTH
from src.engine.resolve import max_run_distance_per_tick, resolve
from src.engine.timing import TICK_DURATION_SECONDS

ATTRIBUTES = {
    AttributeType.POWER: 20,
    AttributeType.AGILITY: 30,
    AttributeType.CONTROL: 40,
    AttributeType.SPEED: 50,
    AttributeType.STRENGTH: 60,
}

# Con SPEED 50 y speed_percentage 1.0: 4 m/s * 0.5 s = 2 metros por tick.
MAX_DISTANCE = max_run_distance_per_tick(ATTRIBUTES[AttributeType.SPEED], 1.0)


def _game_state_valido(my_position: Point2D = Point2D(10, 10)) -> GameState:
    """GameState de ejemplo, con la pelota en movimiento."""
    return GameState(
        ball_position=Point2D(50, 30),
        ball_velocity=Vector2D(1, 0),
        my_position=my_position,
        teammates=[Point2D(5, 5), Point2D(8, 20)],
        opponents=[Point2D(60, 10), Point2D(70, 30), Point2D(80, 50)],
        team_goal=Point2D(0, 30),
        opponent_goal=Point2D(105, 30),
    )


def _run_to(target: Point2D, speed_percentage: float = 1.0) -> Intention:
    return Intention(ActionType.RUN_TO, target=target, speed_percentage=speed_percentage)


def _esta_en_cancha(position: Point2D) -> bool:
    return 0 <= position.x <= PITCH_LENGTH and 0 <= position.y <= PITCH_WIDTH


# --- IDLE ---

def test_deberia_resolve_idle_conservar_la_posicion_del_jugador():
    """Resolver IDLE deja my_position idéntica."""
    estado = _game_state_valido()

    nuevo = resolve(estado, Intention(ActionType.IDLE), ATTRIBUTES)

    assert nuevo.my_position == estado.my_position


def test_deberia_resolve_idle_no_cambiar_el_resto_del_estado():
    """Todo el GameState queda igual, no solo la posición."""
    estado = _game_state_valido()

    assert resolve(estado, Intention(ActionType.IDLE), ATTRIBUTES) == estado


# --- Distancia máxima por tick ---

def test_deberia_distancia_maxima_seguir_la_formula_de_constants():
    """distancia = velocidad máxima * SPEED/100 * speed_percentage * duración del tick."""
    esperada = MAX_RUN_SPEED_METERS_PER_SECOND * (50 / MAX_ATTRIBUTE_VALUE) * 1.0 * TICK_DURATION_SECONDS

    assert max_run_distance_per_tick(50, 1.0) == pytest.approx(esperada)


def test_deberia_mas_speed_permitir_correr_mas_distancia():
    assert max_run_distance_per_tick(100, 1.0) > max_run_distance_per_tick(20, 1.0)


# --- RUN_TO: caso normal ---

def test_deberia_run_to_avanzar_exactamente_la_distancia_maxima_hacia_target_lejano():
    """Target lejano en línea recta (eje x): avanza justo MAX_DISTANCE hacia él."""
    estado = _game_state_valido(Point2D(10, 10))

    nuevo = resolve(estado, _run_to(Point2D(50, 10)), ATTRIBUTES)

    assert nuevo.my_position.x == pytest.approx(10 + MAX_DISTANCE)
    assert nuevo.my_position.y == pytest.approx(10)


def test_deberia_run_to_moverse_en_linea_recta_en_diagonal():
    """Target en diagonal: avanza MAX_DISTANCE sobre la recta que une ambos puntos."""
    inicio = Point2D(10, 10)
    target = Point2D(40, 50)  # está a 50 m (triángulo 30-40-50)

    nuevo = resolve(_game_state_valido(inicio), _run_to(target), ATTRIBUTES)

    assert inicio.distance_to(nuevo.my_position) == pytest.approx(MAX_DISTANCE)
    # Sigue la dirección (0.6, 0.8) del vector inicio -> target.
    assert nuevo.my_position.x == pytest.approx(10 + 0.6 * MAX_DISTANCE)
    assert nuevo.my_position.y == pytest.approx(10 + 0.8 * MAX_DISTANCE)


def test_deberia_run_to_no_cambiar_nada_mas_que_la_posicion_del_jugador():
    estado = _game_state_valido()

    nuevo = resolve(estado, _run_to(Point2D(50, 10)), ATTRIBUTES)

    assert replace(nuevo, my_position=estado.my_position) == estado


@pytest.mark.parametrize("target", [Point2D(50, 10), Point2D(10, 59), Point2D(0, 0), Point2D(200, -50)])
def test_deberia_desplazamiento_nunca_superar_la_distancia_maxima(target):
    estado = _game_state_valido(Point2D(10, 10))

    nuevo = resolve(estado, _run_to(target), ATTRIBUTES)

    assert estado.my_position.distance_to(nuevo.my_position) <= MAX_DISTANCE + 1e-9


# --- RUN_TO: speed_percentage ---

def test_deberia_speed_percentage_menor_dar_desplazamiento_proporcionalmente_menor():
    """Con la mitad de speed_percentage, recorre la mitad de distancia."""
    estado = _game_state_valido(Point2D(10, 10))
    target = Point2D(50, 10)

    a_fondo = resolve(estado, _run_to(target, 1.0), ATTRIBUTES)
    a_la_mitad = resolve(estado, _run_to(target, 0.5), ATTRIBUTES)

    distancia_a_fondo = estado.my_position.distance_to(a_fondo.my_position)
    distancia_a_la_mitad = estado.my_position.distance_to(a_la_mitad.my_position)
    assert distancia_a_la_mitad == pytest.approx(distancia_a_fondo * 0.5)


def test_deberia_speed_percentage_cero_no_mover_al_jugador():
    estado = _game_state_valido(Point2D(10, 10))

    nuevo = resolve(estado, _run_to(Point2D(50, 10), 0.0), ATTRIBUTES)

    assert nuevo.my_position == estado.my_position


# --- RUN_TO: bordes ---

def test_deberia_terminar_en_target_si_esta_mas_cerca_que_la_distancia_maxima():
    """Sin overshoot: si target está a menos del máximo, queda exactamente en target."""
    target = Point2D(10.5, 10.5)  # a ~0.7 m, menos que MAX_DISTANCE (2 m)

    nuevo = resolve(_game_state_valido(Point2D(10, 10)), _run_to(target), ATTRIBUTES)

    assert nuevo.my_position == target


def test_deberia_terminar_en_target_si_esta_justo_a_la_distancia_maxima():
    target = Point2D(10 + MAX_DISTANCE, 10)

    nuevo = resolve(_game_state_valido(Point2D(10, 10)), _run_to(target), ATTRIBUTES)

    assert nuevo.my_position == target


def test_deberia_target_igual_a_la_posicion_actual_no_mover_ni_fallar():
    """Vector cero: no hay dirección, pero no debe dividir por cero."""
    estado = _game_state_valido(Point2D(10, 10))

    nuevo = resolve(estado, _run_to(Point2D(10, 10)), ATTRIBUTES)

    assert nuevo.my_position == Point2D(10, 10)


def test_deberia_quedar_en_el_borde_si_target_esta_fuera_de_la_cancha():
    """Pegado a la línea x=0 y corriendo hacia afuera: queda en el borde, no sale."""
    estado = _game_state_valido(Point2D(1, 30))

    nuevo = resolve(estado, _run_to(Point2D(-50, 30)), ATTRIBUTES)

    assert nuevo.my_position == Point2D(0, 30)


@pytest.mark.parametrize(
    "inicio, target",
    [
        (Point2D(0.5, 30), Point2D(-100, 30)),               # sale por el fondo de HOME
        (Point2D(PITCH_LENGTH - 0.5, 30), Point2D(500, 30)),  # sale por el fondo de AWAY
        (Point2D(50, 0.5), Point2D(50, -100)),                # sale por el lateral y=0
        (Point2D(50, PITCH_WIDTH - 0.5), Point2D(50, 500)),   # sale por el lateral y=60
        (Point2D(0.5, 0.5), Point2D(-100, -100)),             # sale por la esquina
    ],
)
def test_deberia_jugador_nunca_terminar_fuera_de_la_cancha(inicio, target):
    nuevo = resolve(_game_state_valido(inicio), _run_to(target), ATTRIBUTES)

    assert _esta_en_cancha(nuevo.my_position)


# --- KICK_BALL ---
# Con ATTRIBUTES: POWER 20 y CONTROL 40
#   rapidez a fondo = 30 m/s * 20/100 = 6 m/s
#   alcance         = reach_distance(40) = 1.625 m

REACH = reach_distance(ATTRIBUTES[AttributeType.CONTROL])
MAX_KICK_SPEED = MAX_KICK_SPEED_METERS_PER_SECOND * ATTRIBUTES[AttributeType.POWER] / MAX_ATTRIBUTE_VALUE


def _kick(direction: Vector2D, power_percentage: float = 1.0) -> Intention:
    return Intention(ActionType.KICK_BALL, direction=direction, power_percentage=power_percentage)


def _con_pelota_a(distancia: float) -> GameState:
    """Jugador en (0, 0) y pelota en reposo a `distancia` metros sobre el eje x."""
    return replace(
        _game_state_valido(Point2D(0, 0)),
        ball_position=Point2D(distancia, 0),
        ball_velocity=Vector2D(0, 0),
    )


def test_deberia_kick_ball_en_alcance_darle_a_la_pelota_la_direccion_pedida():
    nuevo = resolve(_con_pelota_a(1.0), _kick(Vector2D(0, 1)), ATTRIBUTES)

    assert nuevo.ball_velocity.x == pytest.approx(0.0)
    assert nuevo.ball_velocity.y == pytest.approx(MAX_KICK_SPEED)


def test_deberia_kick_ball_normalizar_la_direccion_antes_de_aplicarla():
    """(30, 40) y (0.3, 0.4) apuntan igual: la velocidad solo depende de power_percentage."""
    grande = resolve(_con_pelota_a(1.0), _kick(Vector2D(30, 40)), ATTRIBUTES)
    chica = resolve(_con_pelota_a(1.0), _kick(Vector2D(0.3, 0.4)), ATTRIBUTES)

    assert grande.ball_velocity.x == pytest.approx(0.6 * MAX_KICK_SPEED)
    assert grande.ball_velocity.y == pytest.approx(0.8 * MAX_KICK_SPEED)
    assert chica.ball_velocity == grande.ball_velocity


def test_deberia_kick_ball_dar_velocidad_proporcional_a_power_percentage():
    a_fondo = resolve(_con_pelota_a(1.0), _kick(Vector2D(1, 0), 1.0), ATTRIBUTES)
    a_la_mitad = resolve(_con_pelota_a(1.0), _kick(Vector2D(1, 0), 0.5), ATTRIBUTES)

    assert a_la_mitad.ball_velocity.magnitude() == pytest.approx(a_fondo.ball_velocity.magnitude() * 0.5)


def test_deberia_kick_ball_con_mas_power_dar_mas_velocidad():
    poco = resolve(_con_pelota_a(1.0), _kick(Vector2D(1, 0)), {**ATTRIBUTES, AttributeType.POWER: 20})
    mucho = resolve(_con_pelota_a(1.0), _kick(Vector2D(1, 0)), {**ATTRIBUTES, AttributeType.POWER: 100})

    assert mucho.ball_velocity.magnitude() > poco.ball_velocity.magnitude()


def test_deberia_kick_ball_pisar_la_velocidad_anterior_de_la_pelota():
    """La patada reemplaza la velocidad (no la suma a la que traía)."""
    estado = replace(_con_pelota_a(1.0), ball_velocity=Vector2D(-9, -9))

    nuevo = resolve(estado, _kick(Vector2D(1, 0)), ATTRIBUTES)

    assert nuevo.ball_velocity.x == pytest.approx(MAX_KICK_SPEED)
    assert nuevo.ball_velocity.y == pytest.approx(0.0)


def test_deberia_kick_ball_no_cambiar_nada_mas_que_ball_velocity():
    estado = _con_pelota_a(1.0)

    nuevo = resolve(estado, _kick(Vector2D(1, 0)), ATTRIBUTES)

    assert replace(nuevo, ball_velocity=estado.ball_velocity) == estado


def test_deberia_kick_ball_fuera_de_alcance_dejar_el_estado_sin_cambios():
    estado = replace(_con_pelota_a(REACH + 0.01), ball_velocity=Vector2D(1, 2))

    assert resolve(estado, _kick(Vector2D(1, 0)), ATTRIBUTES) == estado


def test_deberia_kick_ball_justo_en_el_borde_del_alcance_patear():
    """Borde inclusive: distancia == reach_distance() sí patea."""
    nuevo = resolve(_con_pelota_a(REACH), _kick(Vector2D(1, 0)), ATTRIBUTES)

    assert nuevo.ball_velocity.x == pytest.approx(MAX_KICK_SPEED)


def test_deberia_kick_ball_con_power_percentage_cero_dejar_la_pelota_sin_velocidad():
    estado = replace(_con_pelota_a(1.0), ball_velocity=Vector2D(3, 4))

    nuevo = resolve(estado, _kick(Vector2D(1, 0), 0.0), ATTRIBUTES)

    assert nuevo.ball_velocity.magnitude() == pytest.approx(0.0)


def test_deberia_el_alcance_depender_del_control_del_jugador():
    """A 3 m: con CONTROL 40 (alcance 1.6 m) no llega, con CONTROL 100 (5 m) sí."""
    estado = _con_pelota_a(3.0)

    sin_alcance = resolve(estado, _kick(Vector2D(1, 0)), {**ATTRIBUTES, AttributeType.CONTROL: 40})
    con_alcance = resolve(estado, _kick(Vector2D(1, 0)), {**ATTRIBUTES, AttributeType.CONTROL: 100})

    assert sin_alcance == estado
    assert con_alcance.ball_velocity.magnitude() > 0