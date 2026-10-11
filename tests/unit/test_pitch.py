"""Tests de la regla de gol (pitch.detect_goal)."""

import pytest

from src.engine._01_to_world.data_types import Point2D
from src.engine.pitch import GOAL_WIDTH, PITCH_LENGTH, PITCH_WIDTH, TeamSide, detect_goal

CENTRO_Y = PITCH_WIDTH / 2


def test_deberia_no_haber_gol_con_la_pelota_en_el_centro():
    assert detect_goal(Point2D(PITCH_LENGTH / 2, CENTRO_Y)) is None


def test_deberia_gol_de_home_si_la_pelota_entra_en_el_arco_de_away():
    assert detect_goal(Point2D(PITCH_LENGTH, CENTRO_Y)) is TeamSide.HOME


def test_deberia_gol_de_away_si_la_pelota_entra_en_el_arco_de_home():
    assert detect_goal(Point2D(0.0, CENTRO_Y)) is TeamSide.AWAY


@pytest.mark.parametrize("x", [0.0, PITCH_LENGTH])
def test_deberia_contar_gol_en_el_borde_del_ancho_del_arco(x):
    borde = CENTRO_Y + GOAL_WIDTH / 2

    assert detect_goal(Point2D(x, borde)) is not None


@pytest.mark.parametrize("x", [0.0, PITCH_LENGTH])
def test_deberia_no_contar_gol_si_la_pelota_cruza_la_linea_fuera_del_arco(x):
    assert detect_goal(Point2D(x, CENTRO_Y + GOAL_WIDTH)) is None
