"""Tests de la detección de gol de referencia (pitch.default_detect_goal)."""

import pytest

from src.engine.geometry_types import Point2D, Vector2D
from src.engine.pitch import GOAL_WIDTH, PITCH_LENGTH, PITCH_WIDTH, TeamSide, default_detect_goal
from src.engine.state import BallState, MatchPhase, MatchState, Score

CENTRO_Y = PITCH_WIDTH / 2


def _state_con_pelota_en(x: float, y: float) -> MatchState:
    return MatchState(
        match_id=1,
        phase=MatchPhase.IN_PROGRESS,
        current_tick=0,
        total_ticks=10,
        score=Score(),
        ball=BallState(position=Point2D(x, y), velocity=Vector2D(0.0, 0.0)),
    )


def test_deberia_no_haber_gol_con_la_pelota_en_el_centro():
    assert default_detect_goal(_state_con_pelota_en(PITCH_LENGTH / 2, CENTRO_Y)) is None


def test_deberia_gol_de_home_si_la_pelota_entra_en_el_arco_de_away():
    assert default_detect_goal(_state_con_pelota_en(PITCH_LENGTH, CENTRO_Y)) is TeamSide.HOME


def test_deberia_gol_de_away_si_la_pelota_entra_en_el_arco_de_home():
    assert default_detect_goal(_state_con_pelota_en(0.0, CENTRO_Y)) is TeamSide.AWAY


@pytest.mark.parametrize("x", [0.0, PITCH_LENGTH])
def test_deberia_contar_gol_en_el_borde_del_ancho_del_arco(x):
    borde = CENTRO_Y + GOAL_WIDTH / 2

    assert default_detect_goal(_state_con_pelota_en(x, borde)) is not None


@pytest.mark.parametrize("x", [0.0, PITCH_LENGTH])
def test_deberia_no_contar_gol_si_la_pelota_cruza_la_linea_fuera_del_arco(x):
    assert default_detect_goal(_state_con_pelota_en(x, CENTRO_Y + GOAL_WIDTH)) is None
