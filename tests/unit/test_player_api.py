"""
Tests de PlayerAPI (T1): getters sobre un snapshot e intención idle().
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
    """
    Política: gana la última llamada. Se pisa la intención directamente
    porque run_to todavía no existe; cuando exista, reemplazar por
    api.run_to(...) seguido de api.idle().
    """
    api = PlayerAPI(_game_state_valido(), ATTRIBUTES)
    api._intention = Intention(ActionType.RUN_TO, target=Point2D(1, 1), speed_percentage=1.0)

    api.idle()

    assert api.intention.action == ActionType.IDLE


def test_deberia_dos_playerapi_no_compartir_la_intencion():
    """La intención es de instancia: tocar una API no afecta a la otra."""
    estado = _game_state_valido()
    api_a, api_b = PlayerAPI(estado, ATTRIBUTES), PlayerAPI(estado, ATTRIBUTES)
    api_a._intention = Intention(ActionType.KICK_BALL)

    api_a.idle()

    assert api_b.intention.action == ActionType.IDLE
