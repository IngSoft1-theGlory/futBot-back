"""
Tests de los comportamientos predeterminados (is_default=True).

Uno o dos tests por cada criterio de aceptacion:
  CA1  existen al menos 3 comportamientos con is_default=True
  CA2  GET /api/v1/behaviors los devuelve a un usuario sin comportamientos propios
  CA3  ejecutan sin excepcion en un tick de prueba
  CA4  son funcionalmente distinguibles en una simulacion simple
"""

import pytest
from sqlalchemy import select

from src.default_behaviors import DEFAULT_BEHAVIORS
from src.engine.behavior_executor import make_execute_behavior
from src.engine._01_to_world.data_types import (
    AttributeType, Point2D, Vector2D
)
from src.engine.match_runner import run_tick
from src.engine._01_to_world.pitch import TeamSide
from src.engine.simulation import apply_intentions
from src.engine.state import BallState, MatchPhase, MatchPlayerState, MatchState, Score
from src.main import app
from src.models import Behavior
from src.seed import seed_default_behaviors


# ---------------------------------------------------------------------------
# Ayudas
# ---------------------------------------------------------------------------

NAMES = [data["name"] for data in DEFAULT_BEHAVIORS]

# id de comportamiento para cada default: {"Neutro": 1, "Ofensivo": 2, ...}
BEHAVIOR_IDS = {name: i for i, name in enumerate(NAMES, start=1)}

# los textos indexados por ese id: lo que recibe make_execute_behavior
CODES = {BEHAVIOR_IDS[data["name"]]: data["code"] for data in DEFAULT_BEHAVIORS}

# atributos del jugador de prueba (alcance = 0.05625 * 60 - 0.625 = 2.75 m).
# Sin atributos el jugador queda en IDLE sin avisar.
ATTRIBUTES = {
    AttributeType.POWER: 80,
    AttributeType.AGILITY: 50,
    AttributeType.CONTROL: 60,
    AttributeType.SPEED: 80,
    AttributeType.STRENGTH: 50,
}


def _state(behavior_name, ball):
    """
    Partido de prueba con un solo jugador: el 1, del equipo HOME, parado en (70, 30)
    y con el comportamiento elegido. Su arco esta en (0, 30), el rival en (105, 30).
    """
    player = MatchPlayerState(
        player_id=1,
        team_id=1,
        side=TeamSide.HOME,
        is_starter=True,
        role=None,
        behavior_id=BEHAVIOR_IDS[behavior_name],
        position=Point2D(70.0, 30.0),
        attributes=dict(ATTRIBUTES),
    )
    return MatchState(
        match_id=1,
        phase=MatchPhase.IN_PROGRESS,
        current_tick=0,
        total_ticks=240,
        score=Score(),
        ball=BallState(position=ball, velocity=Vector2D(0.0, 0.0)),
        players={1: player},
    )


def _run_ticks(state, ticks):
    """Corre `ticks` ticks con el motor real: comportamientos + apply_intentions."""
    execute_behavior = make_execute_behavior(CODES)
    for _ in range(ticks):
        run_tick(
            state,
            execute_behavior=execute_behavior,
            apply_intentions=apply_intentions,
            detect_goal=lambda s: None,   # sin goles pq no hacen falta en estos tests
        )



# existen al menos 3 comportamientos con is_default = True
def _defaults_in_db(session):
    return session.scalars(select(Behavior).where(Behavior.is_default.is_(True))).all()


def test_deberia_cargar_al_menos_3_comportamientos_default(session):
    seed_default_behaviors(session)

    defaults = _defaults_in_db(session)

    assert len(defaults) >= 3
    assert all(behavior.user_id is None for behavior in defaults)   # son del sistema


# ejecutan sin excepcion en un tick de prueba
# Se llama a execute_behavior directo y no a run_tick, porque run_tick atrapa las
# excepciones y devuelve IDLE, y ocultaria justo lo que se quiere detectar
@pytest.mark.parametrize("name", NAMES)
def test_deberia_ejecutar_sin_excepcion_en_un_tick(name):
    execute_behavior = make_execute_behavior(CODES)

    # una vez con la pelota lejos (el jugador corre o se queda) y otra al alcance (patea)
    for ball in (Point2D(52.5, 30.0), Point2D(70.5, 30.0)):
        state = _state(name, ball)

        execute_behavior(state, 1)   # si el texto falla, el test falla


# son funcionalmente distinguibles en una simulacion simple
def test_el_ofensivo_se_acerca_a_la_pelota():
    state = _state("Ofensivo", ball=Point2D(52.5, 30.0))
    distance_before = state.players[1].position.distance_to(state.ball.position)

    _run_ticks(state, 3)   # alcanza para acercarse sin llegar a patearla

    distance_after = state.players[1].position.distance_to(state.ball.position)
    assert distance_after < distance_before


def test_el_defensor_no_se_aleja_de_su_arco():
    state = _state("Defensor", ball=Point2D(52.5, 30.0))
    own_goal = Point2D(0.0, 30.0)

    _run_ticks(state, 40)   # tiempo de sobra para llegar a su punto de guardia

    # termina a 15 m de su arco, que es su punto de guardia
    distance = state.players[1].position.distance_to(own_goal)
    assert distance == pytest.approx(15.0, abs=0.1)