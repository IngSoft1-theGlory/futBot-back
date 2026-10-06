"""
Tests de PlayerAPI: getters sobre un snapshot, idle(), run_to() y kick_ball().
Trabajan con snapshots armados a mano: sin base de datos ni motor.
"""

from dataclasses import FrozenInstanceError

import pytest

from src.engine.game_types import AttributeType, GameState
from src.engine.geometry_types import Point2D, Vector2D
from src.engine.intentions import ActionType, Intention
from src.engine.player_api import PlayerAPI

# Todos distintos, para detectar cruces entre atributos.
ATTRIBUTES = {
    AttributeType.POWER: 20,
    AttributeType.AGILITY: 30,
    AttributeType.CONTROL: 40,
    AttributeType.SPEED: 50,
    AttributeType.STRENGTH: 60,
}


def _game_state_valido() -> GameState:
    """GameState de ejemplo: 2 compañeros y 3 rivales."""
    return GameState(
        ball_position=Point2D(50, 30),
        ball_velocity=Vector2D(0, 0),
        my_position=Point2D(10, 10),
        teammates=[Point2D(5, 5), Point2D(8, 20)],
        opponents=[Point2D(60, 10), Point2D(70, 30), Point2D(80, 50)],
        team_goal=Point2D(0, 30),
        opponent_goal=Point2D(105, 30),
    )


def test_deberia_game_state_ser_inmutable():
    """frozen=True: asignar un campo del GameState lanza FrozenInstanceError."""
    estado = _game_state_valido()

    with pytest.raises(FrozenInstanceError):
        estado.my_position = Point2D(0, 0)


def test_deberia_get_game_state_devolver_el_snapshot_recibido():
    """El getter lee del snapshot con el que se construyó, no de otro lado."""
    estado = _game_state_valido()
    api = PlayerAPI(estado, ATTRIBUTES)

    assert api.get_game_state() is estado


@pytest.mark.parametrize("atributo", list(AttributeType))
def test_deberia_get_attribute_devolver_el_valor_del_snapshot(atributo):
    """Para cada AttributeType devuelve exactamente su valor, no el de otro."""
    api = PlayerAPI(_game_state_valido(), ATTRIBUTES)

    assert api.get_attribute(atributo) == ATTRIBUTES[atributo]


def test_deberia_sin_llamar_a_ninguna_primitiva_la_intencion_ser_idle():
    """Si on_tick no llama a nada, la intención resultante es IDLE."""
    api = PlayerAPI(_game_state_valido(), ATTRIBUTES)

    assert api.intention.action == ActionType.IDLE


def test_deberia_idle_registrar_intencion_idle():
    """idle() deja registrada una Intention de tipo IDLE."""
    api = PlayerAPI(_game_state_valido(), ATTRIBUTES)

    api.idle()

    assert api.intention.action == ActionType.IDLE


def test_deberia_llamadas_multiples_en_un_tick_ganar_la_ultima():
    """Política: gana la última llamada (run_to y después idle -> IDLE)."""
    api = PlayerAPI(_game_state_valido(), ATTRIBUTES)
    api.run_to(Point2D(1, 1), 1.0)

    api.idle()

    assert api.intention.action == ActionType.IDLE


def test_deberia_idle_y_despues_run_to_quedar_en_run_to():
    api = PlayerAPI(_game_state_valido(), ATTRIBUTES)
    api.idle()

    api.run_to(Point2D(1, 1), 1.0)

    assert api.intention.action == ActionType.RUN_TO


def test_deberia_dos_playerapi_no_compartir_la_intencion():
    """La intención es de instancia: tocar una API no afecta a la otra."""
    estado = _game_state_valido()
    api_a, api_b = PlayerAPI(estado, ATTRIBUTES), PlayerAPI(estado, ATTRIBUTES)
    api_a._intention = Intention(ActionType.KICK_BALL)

    api_a.idle()

    assert api_b.intention.action == ActionType.IDLE


# --- run_to ---

def test_deberia_run_to_registrar_intencion_con_target_y_speed_percentage():
    api = PlayerAPI(_game_state_valido(), ATTRIBUTES)

    api.run_to(Point2D(50, 30), 0.75)

    assert api.intention == Intention(ActionType.RUN_TO, target=Point2D(50, 30), speed_percentage=0.75)


@pytest.mark.parametrize("speed_percentage", [0.0, 0.5, 1.0, 0, 1])
def test_deberia_run_to_aceptar_speed_percentage_entre_cero_y_uno(speed_percentage):
    """Los extremos 0.0 y 1.0 son válidos; también los enteros 0 y 1."""
    api = PlayerAPI(_game_state_valido(), ATTRIBUTES)

    api.run_to(Point2D(50, 30), speed_percentage)

    assert api.intention.action == ActionType.RUN_TO
    assert api.intention.speed_percentage == float(speed_percentage)


def test_deberia_run_to_aceptar_target_fuera_de_la_cancha():
    """Target fuera de la cancha es válido: el resolver lo limita al borde."""
    api = PlayerAPI(_game_state_valido(), ATTRIBUTES)

    api.run_to(Point2D(-10, 500), 1.0)

    assert api.intention.action == ActionType.RUN_TO


@pytest.mark.parametrize(
    "target",
    [
        None,
        (50, 30),                        # tupla, no Point2D
        Point2D(float("nan"), 30),
        Point2D(50, float("inf")),
        Point2D(float("-inf"), 30),
        Point2D("50", 30),               # coordenada que no es número
    ],
)
def test_deberia_run_to_con_target_invalido_lanzar_value_error(target):
    api = PlayerAPI(_game_state_valido(), ATTRIBUTES)

    with pytest.raises(ValueError):
        api.run_to(target, 1.0)


@pytest.mark.parametrize(
    "speed_percentage",
    [-0.1, 1.1, 100, float("nan"), float("inf"), None, "1.0", True],
)
def test_deberia_run_to_con_speed_percentage_invalido_lanzar_value_error(speed_percentage):
    api = PlayerAPI(_game_state_valido(), ATTRIBUTES)

    with pytest.raises(ValueError):
        api.run_to(Point2D(50, 30), speed_percentage)


def test_deberia_run_to_invalido_dejar_la_intencion_en_idle():
    """Aunque antes hubiera un run_to válido, una llamada inválida deja IDLE."""
    api = PlayerAPI(_game_state_valido(), ATTRIBUTES)
    api.run_to(Point2D(50, 30), 1.0)

    with pytest.raises(ValueError):
        api.run_to(Point2D(50, 30), 2.0)

    assert api.intention.action == ActionType.IDLE


# --- kick_ball ---

def test_deberia_kick_ball_registrar_intencion_con_direction_y_power_percentage():
    api = PlayerAPI(_game_state_valido(), ATTRIBUTES)

    api.kick_ball(Vector2D(1, 0), 0.75)

    assert api.intention == Intention(ActionType.KICK_BALL, direction=Vector2D(1, 0), power_percentage=0.75)


def test_deberia_kick_ball_registrar_la_direccion_sin_normalizar():
    """Normalizar es trabajo del resolver: la intención guarda lo que pidió el comportamiento."""
    api = PlayerAPI(_game_state_valido(), ATTRIBUTES)

    api.kick_ball(Vector2D(30, 40), 1.0)

    assert api.intention.direction == Vector2D(30, 40)


def test_deberia_kick_ball_registrar_la_intencion_sin_mirar_la_distancia_a_la_pelota():
    """La pelota está a ~40 m (fuera de alcance) y igual se registra: decide resolve."""
    api = PlayerAPI(_game_state_valido(), ATTRIBUTES)

    api.kick_ball(Vector2D(1, 0), 1.0)

    assert api.intention.action == ActionType.KICK_BALL


@pytest.mark.parametrize("power_percentage", [0.0, 0.5, 1.0, 0, 1])
def test_deberia_kick_ball_aceptar_power_percentage_entre_cero_y_uno(power_percentage):
    """Los extremos 0.0 y 1.0 son válidos; también los enteros 0 y 1."""
    api = PlayerAPI(_game_state_valido(), ATTRIBUTES)

    api.kick_ball(Vector2D(1, 0), power_percentage)

    assert api.intention.action == ActionType.KICK_BALL
    assert api.intention.power_percentage == float(power_percentage)


@pytest.mark.parametrize(
    "direction",
    [
        None,
        (1, 0),                          # tupla, no Vector2D
        Point2D(1, 0),                   # Point2D tampoco es un Vector2D
        Vector2D(float("nan"), 0),
        Vector2D(1, float("inf")),
        Vector2D(float("-inf"), 1),
        Vector2D("1", 0),                # componente que no es número
        Vector2D(0, 0),                  # magnitud cero: no hay hacia dónde patear
        Vector2D(0.0, -0.0),
    ],
)
def test_deberia_kick_ball_con_direccion_invalida_lanzar_value_error(direction):
    api = PlayerAPI(_game_state_valido(), ATTRIBUTES)

    with pytest.raises(ValueError):
        api.kick_ball(direction, 1.0)


@pytest.mark.parametrize(
    "power_percentage",
    [-0.1, 1.1, 100, float("nan"), float("inf"), None, "1.0", True],
)
def test_deberia_kick_ball_con_power_percentage_invalido_lanzar_value_error(power_percentage):
    api = PlayerAPI(_game_state_valido(), ATTRIBUTES)

    with pytest.raises(ValueError):
        api.kick_ball(Vector2D(1, 0), power_percentage)


def test_deberia_kick_ball_invalido_dejar_la_intencion_en_idle():
    """Aunque antes hubiera un kick_ball válido, una llamada inválida deja IDLE."""
    api = PlayerAPI(_game_state_valido(), ATTRIBUTES)
    api.kick_ball(Vector2D(1, 0), 1.0)

    with pytest.raises(ValueError):
        api.kick_ball(Vector2D(1, 0), 2.0)

    assert api.intention.action == ActionType.IDLE


def test_deberia_kick_ball_y_despues_run_to_ganar_la_ultima_llamada():
    api = PlayerAPI(_game_state_valido(), ATTRIBUTES)
    api.kick_ball(Vector2D(1, 0), 1.0)

    api.run_to(Point2D(1, 1), 1.0)

    assert api.intention.action == ActionType.RUN_TO