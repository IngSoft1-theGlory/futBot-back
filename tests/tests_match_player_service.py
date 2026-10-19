import pytest

from src.core.exceptions import InvalidConfigurationError, PlayerNotFoundError
from src.engine._01_to_world.data_types import Point2D, Vector2D
from src.engine._01_to_world.pitch import TeamSide
from src.engine._02_to_match.state import (
    BallState, MatchPhase, MatchPlayerState, MatchState, Score, match_registry,
)
from src.services.match_player_service import apply_behavior_change

MATCH_ID = 999
MI_EQUIPO = 1
EQUIPO_RIVAL = 2
CODIGO_VALIDO = "def on_tick(api):\n    pass\n"

def armar_partido():
    jugadores = {
        1: MatchPlayerState(player_id=1, team_id=MI_EQUIPO, side=TeamSide.HOME,
                            is_starter=True, role="DEFENSOR", behavior_id=5),
        2: MatchPlayerState(player_id=2, team_id=EQUIPO_RIVAL, side=TeamSide.AWAY,
                            is_starter=True, role="DEFENSOR", behavior_id=5),
    }
    state = MatchState(
        match_id=MATCH_ID, phase=MatchPhase.IN_PROGRESS, current_tick=0, total_ticks=100,
        score=Score(), ball=BallState(Point2D(0.0, 0.0), Vector2D(0.0, 0.0)),
        players=jugadores,
    )
    match_registry.remove(MATCH_ID)  # por si quedo uno de un test anterior
    match_registry.add(state)
    return state

def test_deberia_asignar_el_comportamiento_nuevo_al_jugador():
    partido = armar_partido()

    apply_behavior_change(MATCH_ID, MI_EQUIPO, CODIGO_VALIDO, 1, 7)

    assert partido.players[1].behavior_id == 7
    assert partido.players[1].on_tick is not None


def test_deberia_fallar_si_el_jugador_no_existe_en_el_partido():
    armar_partido()

    with pytest.raises(PlayerNotFoundError):
        apply_behavior_change(MATCH_ID, MI_EQUIPO, CODIGO_VALIDO, 99, 7)


def test_deberia_fallar_si_el_jugador_es_del_equipo_rival():
    armar_partido()

    with pytest.raises(PlayerNotFoundError):
        apply_behavior_change(MATCH_ID, MI_EQUIPO, CODIGO_VALIDO, 2, 7)


def test_deberia_conservar_el_comportamiento_anterior_si_el_codigo_falla():
    partido = armar_partido()

    with pytest.raises(InvalidConfigurationError):
        apply_behavior_change(MATCH_ID, MI_EQUIPO, "x = 5", 1, 7)

    assert partido.players[1].behavior_id == 5

# match not found y behavior not found son errores que salen de get_match_in_progress y get_behavior, que ya tienen tests propios