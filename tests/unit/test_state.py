"""
Tests de MatchState: construcción del estado inicial y MatchRegistry.
Trabajan con TeamMatchSetup armados a mano: sin base de datos ni motor.
"""

from dataclasses import replace

import pytest

from src.engine.game_types import AttributeType
from src.engine.pitch import TeamSide
from src.engine._02_to_match.state import (
    MatchInitializationError,
    MatchPhase,
    MatchRegistry,
    TeamMatchSetup,
    attributes_of,
    build_initial_state,
)
from src.schemas.lineup_config import LineupConfig, StartingPlayer, SubstitutePlayer

MATCH_ID = 1
TOTAL_TICKS = 1200

ATTRIBUTES = {
    AttributeType.POWER: 80,
    AttributeType.AGILITY: 50,
    AttributeType.CONTROL: 60,
    AttributeType.SPEED: 80,
    AttributeType.STRENGTH: 50,
}


def _attributes(*player_ids: int) -> dict[int, dict[AttributeType, int]]:
    """Los mismos atributos para cada jugador pedido."""
    return {player_id: dict(ATTRIBUTES) for player_id in player_ids}


def _starter(player_id: int, role: str, behavior_id: int = 1) -> StartingPlayer:
    return StartingPlayer(player_id=player_id, role=role, behavior_id=behavior_id)


def _substitute(player_id: int, behavior_id: int = 1) -> SubstitutePlayer:
    return SubstitutePlayer(player_id=player_id, behavior_id=behavior_id)


def _home_setup(formation_type: str = "2-1") -> TeamMatchSetup:
    if formation_type == "2-1":
        starters = [
            _starter(101, "DEF_LEFT"),
            _starter(102, "DEF_RIGHT"),
            _starter(103, "FORWARD"),
        ]
    else:
        starters = [
            _starter(101, "DEFENDER"),
            _starter(102, "FORWARD_LEFT"),
            _starter(103, "FORWARD_RIGHT"),
        ]
    substitutes = [_substitute(104), _substitute(105), _substitute(106)]
    lineup = LineupConfig(
        formation_type=formation_type, starting_players=starters, substitute_players=substitutes
    )
    return TeamMatchSetup(
        team_id=1, side=TeamSide.HOME, lineup=lineup,
        attributes=_attributes(101, 102, 103, 104, 105, 106),
    )


def _away_setup(formation_type: str = "1-2") -> TeamMatchSetup:
    if formation_type == "2-1":
        starters = [
            _starter(201, "DEF_LEFT"),
            _starter(202, "DEF_RIGHT"),
            _starter(203, "FORWARD"),
        ]
    else:
        starters = [
            _starter(201, "DEFENDER"),
            _starter(202, "FORWARD_LEFT"),
            _starter(203, "FORWARD_RIGHT"),
        ]
    substitutes = [_substitute(204), _substitute(205), _substitute(206)]
    lineup = LineupConfig(
        formation_type=formation_type, starting_players=starters, substitute_players=substitutes
    )
    return TeamMatchSetup(
        team_id=2, side=TeamSide.AWAY, lineup=lineup,
        attributes=_attributes(201, 202, 203, 204, 205, 206),
    )


# --- build_initial_state: camino feliz ---


def test_deberia_arrancar_con_tick_cero():
    state = build_initial_state(MATCH_ID, TOTAL_TICKS, _home_setup(), _away_setup())
    assert state.current_tick == 0


def test_deberia_arrancar_con_marcador_0_a_0():
    state = build_initial_state(MATCH_ID, TOTAL_TICKS, _home_setup(), _away_setup())
    assert state.score.home == 0
    assert state.score.away == 0


def test_deberia_arrancar_en_fase_in_progress():
    state = build_initial_state(MATCH_ID, TOTAL_TICKS, _home_setup(), _away_setup())
    assert state.phase == MatchPhase.IN_PROGRESS


def test_deberia_ubicar_la_pelota_en_el_centro_de_la_cancha():
    state = build_initial_state(MATCH_ID, TOTAL_TICKS, _home_setup(), _away_setup())
    assert state.ball.position.x == pytest.approx(52.5)
    assert state.ball.position.y == pytest.approx(30.0)


def test_deberia_ubicar_a_los_titulares_dentro_de_la_cancha():
    state = build_initial_state(MATCH_ID, TOTAL_TICKS, _home_setup(), _away_setup())
    for player_id in (101, 102, 103, 201, 202, 203):
        assert state.players[player_id].position is not None


def test_deberia_dejar_a_los_suplentes_fuera_de_la_cancha():
    state = build_initial_state(MATCH_ID, TOTAL_TICKS, _home_setup(), _away_setup())
    for player_id in (104, 105, 106, 204, 205, 206):
        assert state.players[player_id].position is None


# --- build_initial_state: validaciones ---


def test_deberia_fallar_si_los_dos_equipos_son_el_mismo():
    home = _home_setup()
    away = replace(_away_setup(), team_id=1)
    with pytest.raises(MatchInitializationError):
        build_initial_state(MATCH_ID, TOTAL_TICKS, home, away)


def test_deberia_fallar_si_los_dos_equipos_defienden_el_mismo_lado():
    home = _home_setup()
    away = replace(_away_setup(), side=TeamSide.HOME)
    with pytest.raises(MatchInitializationError):
        build_initial_state(MATCH_ID, TOTAL_TICKS, home, away)


@pytest.mark.parametrize("total_ticks", [0, -1])
def test_deberia_fallar_si_total_ticks_no_es_positivo(total_ticks):
    with pytest.raises(MatchInitializationError):
        build_initial_state(MATCH_ID, total_ticks, _home_setup(), _away_setup())

# --- atributos de los jugadores ---


def test_deberia_guardar_la_posicion_inicial_de_los_titulares():
    state = build_initial_state(1, 10, _home_setup(), _away_setup())

    titulares = [p for p in state.players.values() if p.is_starter]
    assert titulares
    assert all(p.initial_position == p.position for p in titulares)

def test_deberia_cargar_los_atributos_en_titulares_y_suplentes():
    state = build_initial_state(MATCH_ID, TOTAL_TICKS, _home_setup(), _away_setup())

    for player_id in (101, 103, 104, 106, 201, 203, 204, 206):
        assert state.players[player_id].attributes == ATTRIBUTES


def test_deberia_dar_a_cada_jugador_su_propio_dict_de_atributos():
    setup = _home_setup()
    state = build_initial_state(MATCH_ID, TOTAL_TICKS, setup, _away_setup())

    state.players[101].attributes[AttributeType.SPEED] = 1   # modifico uno

    assert state.players[102].attributes[AttributeType.SPEED] == 80   # los otros no cambian
    assert setup.attributes[101][AttributeType.SPEED] == 80           # el setup tampoco


def test_deberia_fallar_si_faltan_los_atributos_de_un_jugador():
    sin_el_103 = replace(_home_setup(), attributes=_attributes(101, 102, 104, 105, 106))

    with pytest.raises(MatchInitializationError):
        build_initial_state(MATCH_ID, TOTAL_TICKS, sin_el_103, _away_setup())


def test_deberia_pasar_los_atributos_de_un_player_al_dict_del_motor():
    class FakePlayer:   # lo mismo que tiene el modelo Player
        power, agility, control, speed, strength = 80, 50, 60, 70, 40

    assert attributes_of(FakePlayer()) == {
        AttributeType.POWER: 80,
        AttributeType.AGILITY: 50,
        AttributeType.CONTROL: 60,
        AttributeType.SPEED: 70,
        AttributeType.STRENGTH: 40,
    }


# --- MatchRegistry ---


def test_deberia_registry_devolver_none_si_no_existe_el_match():
    registry = MatchRegistry()
    assert registry.get(999) is None


def test_deberia_registry_guardar_y_devolver_el_mismo_estado():
    registry = MatchRegistry()
    state = build_initial_state(MATCH_ID, TOTAL_TICKS, _home_setup(), _away_setup())

    registry.add(state)

    assert registry.get(MATCH_ID) is state

def test_deberia_registry_no_devolver_nada_tras_remove():
    registry = MatchRegistry()
    state = build_initial_state(MATCH_ID, TOTAL_TICKS, _home_setup(), _away_setup())
    registry.add(state)

    registry.remove(MATCH_ID)

    assert registry.get(MATCH_ID) is None

