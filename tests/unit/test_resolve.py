"""
Tests del resolve: aplica una Intention a un GameState.
Por ahora solo IDLE;
"""

import pytest

from src.engine.game_types import GameState
from src.engine.geometry_types import Point2D, Vector2D
from src.engine.intentions import ActionType, Intention
from src.engine.resolve import resolve


def _game_state_valido() -> GameState:
    """GameState de ejemplo, con la pelota en movimiento."""
    return GameState(
        ball_position=Point2D(50, 30),
        ball_velocity=Vector2D(1, 0),
        my_position=Point2D(10, 10),
        teammates=[Point2D(5, 5), Point2D(8, 20)],
        opponents=[Point2D(60, 10), Point2D(70, 30), Point2D(80, 50)],
        team_goal=Point2D(0, 30),
        opponent_goal=Point2D(105, 30),
    )


def test_deberia_resolve_idle_conservar_la_posicion_del_jugador():
    """Resolver IDLE deja my_position idéntica."""
    estado = _game_state_valido()

    nuevo = resolve(estado, Intention(ActionType.IDLE))

    assert nuevo.my_position == estado.my_position


def test_deberia_resolve_idle_no_cambiar_el_resto_del_estado():
    """Todo el GameState queda igual, no solo la posición."""
    estado = _game_state_valido()

    assert resolve(estado, Intention(ActionType.IDLE)) == estado


def test_deberia_resolve_accion_no_implementada_fallar_en_vez_de_ignorarla():
    """RUN_TO todavía no se resuelve: lanza NotImplementedError (no pasa en silencio)."""
    with pytest.raises(NotImplementedError):
        resolve(_game_state_valido(), Intention(ActionType.RUN_TO))
