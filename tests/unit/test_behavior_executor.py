import pytest

from src.engine._01_to_world.data_types import ActionType, Point2D, Vector2D
from src.engine._01_to_world.pitch import TeamSide
from src.engine._02_to_match.state import BallState, MatchPhase, MatchPlayerState, MatchState, Score
from src.engine._03_to_builder.behavior_executor import assign_behavior, execute_behavior


def crear_jugador(player_id=1, behavior_id=1, on_tick=None):
    """Jugador de prueba: titular HOME en (20, 20). Solo cambian su id, su comportamiento y su on_tick."""
    return MatchPlayerState(
        player_id=player_id,
        team_id=1,
        side=TeamSide.HOME,
        is_starter=True,
        role=None,
        behavior_id=behavior_id,
        position=Point2D(20, 20),
        on_tick=on_tick,
    )


def test_deberia_asignar_behavior_id_y_on_tick_con_codigo_valido():
    jugador = crear_jugador(behavior_id=1)  # arranca con el comportamiento 1 y sin on_tick

    assign_behavior(jugador, 2, "def on_tick(api):\n    return 'ejecutado'")

    assert jugador.behavior_id == 2  # cambio el id
    assert callable(jugador.on_tick)  # y guardo una funcion
    assert jugador.on_tick(None) == "ejecutado"  # ademas de ser callable, se puede ejecutar


def test_deberia_conservar_el_comportamiento_anterior_si_el_codigo_es_invalido():
    def on_tick_anterior(api):
        return "anterior"

    jugador = crear_jugador(behavior_id=1, on_tick=on_tick_anterior)

    # codigo invalido porque no hace def on_tick
    with pytest.raises(ValueError):
        assign_behavior(jugador, 2, "x = 1")

    # chequeo que conserva su comportamiento anterior
    assert jugador.behavior_id == 1
    assert jugador.on_tick is on_tick_anterior  

def test_deberia_devolver_la_intencion_de_cada_jugador_segun_su_funcion():
    # dos comportamientos distintos
    def quedarse(api):
        api.idle()

    def correr(api):
        api.run_to(Point2D(10, 10), 0.5)

    # partido con dos jugadores, cada uno con su propia funcion
    state = MatchState(
        match_id=1,
        phase=MatchPhase.IN_PROGRESS,
        current_tick=0,
        total_ticks=100,
        score=Score(),
        ball=BallState(position=Point2D(50, 25), velocity=Vector2D(0, 0)),
        players={1: crear_jugador(1, 1, quedarse), 2: crear_jugador(2, 2, correr)},
    )

    intencion_1 = execute_behavior(state, 1)
    intencion_2 = execute_behavior(state, 2)

    # chequeo que cada jugador devolvio lo que decidio su funcion
    assert intencion_1.action == ActionType.IDLE
    assert intencion_2.action == ActionType.RUN_TO
    assert intencion_2.target == Point2D(10, 10)