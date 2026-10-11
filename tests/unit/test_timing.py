"""Tests de la conversión match_duration -> total_ticks."""

import pytest

from src.engine._01_to_world.metrics import TICK_DURATION_SECONDS, total_ticks_for


def test_deberia_tick_durar_medio_segundo():
    assert TICK_DURATION_SECONDS == 0.5


@pytest.mark.parametrize(
    "minutos, ticks_esperados",
    [
        (2, 240),
        (5, 600),
    ],
)
def test_deberia_convertir_minutos_a_ticks(minutos, ticks_esperados):
    assert total_ticks_for(minutos) == ticks_esperados


def test_deberia_el_maximo_ser_600_ticks():
    """5 minutos es la duración más larga permitida por el contrato."""
    assert total_ticks_for(5) == 600
