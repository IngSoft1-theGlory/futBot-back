"""
Tests de MatchState: construcción del estado inicial y MatchRegistry.
Trabajan con TeamMatchSetup armados a mano: sin base de datos ni motor.
"""

import pytest

from src.engine.pitch import TeamSide
from src.engine.state import (
    LineupPlayer,
    MatchInitializationError,
    MatchPhase,
    MatchRegistry,
    TeamMatchSetup,
    build_initial_state,
)

MATCH_ID = 1
TOTAL_TICKS = 1200


def _starter(player_id: int, role: str, behavior_id: int = 1) -> LineupPlayer:
    return LineupPlayer(player_id=player_id, is_starter=True, role=role, behavior_id=behavior_id)


def _substitute(player_id: int, behavior_id: int = 1) -> LineupPlayer:
    return LineupPlayer(player_id=player_id, is_starter=False, role=None, behavior_id=behavior_id)


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
    return TeamMatchSetup(
        team_id=1, formation_type=formation_type, side=TeamSide.HOME, players=starters + substitutes
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
    return TeamMatchSetup(
        team_id=2, formation_type=formation_type, side=TeamSide.AWAY, players=starters + substitutes
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


def test_deberia_contener_los_12_jugadores_de_ambos_equipos():
    state = build_initial_state(MATCH_ID, TOTAL_TICKS, _home_setup(), _away_setup())
    assert len(state.players) == 12
    assert len(state.players_of(1)) == 6
    assert len(state.players_of(2)) == 6


def test_deberia_ubicar_a_los_titulares_dentro_de_la_cancha():
    state = build_initial_state(MATCH_ID, TOTAL_TICKS, _home_setup(), _away_setup())
    for player_id in (101, 102, 103, 201, 202, 203):
        assert state.players[player_id].position is not None


def test_deberia_dejar_a_los_suplentes_fuera_de_la_cancha():
    state = build_initial_state(MATCH_ID, TOTAL_TICKS, _home_setup(), _away_setup())
    for player_id in (104, 105, 106, 204, 205, 206):
        assert state.players[player_id].position is None


def test_deberia_reflejar_el_lado_de_cancha_en_la_posicion_del_titular():
    """Un DEF_LEFT de HOME y uno de AWAY (si jugaran la misma formación)
    deben quedar en lados opuestos, no en la misma posición."""
    home = _home_setup("2-1")
    away = TeamMatchSetup(
        team_id=2,
        formation_type="2-1",
        side=TeamSide.AWAY,
        players=[_starter(201, "DEF_LEFT"), _starter(202, "DEF_RIGHT"), _starter(203, "FORWARD")]
        + [_substitute(204), _substitute(205), _substitute(206)],
    )
    state = build_initial_state(MATCH_ID, TOTAL_TICKS, home, away)

    home_def_left = state.players[101].position
    away_def_left = state.players[201].position
    assert home_def_left != away_def_left
    # Están reflejados: la suma de sus x es el largo de la cancha, la de sus y el ancho.
    assert home_def_left.x + away_def_left.x == pytest.approx(105.0)
    assert home_def_left.y + away_def_left.y == pytest.approx(60.0)


# --- build_initial_state: validaciones ---


def test_deberia_fallar_si_los_dos_equipos_son_el_mismo():
    home = _home_setup()
    away = TeamMatchSetup(team_id=1, formation_type="1-2", side=TeamSide.AWAY, players=_away_setup().players)
    with pytest.raises(MatchInitializationError):
        build_initial_state(MATCH_ID, TOTAL_TICKS, home, away)


def test_deberia_fallar_si_los_dos_equipos_defienden_el_mismo_lado():
    home = _home_setup()
    away = TeamMatchSetup(team_id=2, formation_type="1-2", side=TeamSide.HOME, players=_away_setup().players)
    with pytest.raises(MatchInitializationError):
        build_initial_state(MATCH_ID, TOTAL_TICKS, home, away)


@pytest.mark.parametrize("total_ticks", [0, -1])
def test_deberia_fallar_si_total_ticks_no_es_positivo(total_ticks):
    with pytest.raises(MatchInitializationError):
        build_initial_state(MATCH_ID, total_ticks, _home_setup(), _away_setup())


def test_deberia_fallar_si_faltan_titulares():
    home = TeamMatchSetup(
        team_id=1,
        formation_type="2-1",
        side=TeamSide.HOME,
        players=[_starter(101, "DEF_LEFT"), _starter(102, "DEF_RIGHT")]
        + [_substitute(104), _substitute(105), _substitute(106)],
    )
    with pytest.raises(MatchInitializationError):
        build_initial_state(MATCH_ID, TOTAL_TICKS, home, _away_setup())


def test_deberia_fallar_si_la_formacion_no_existe():
    home = TeamMatchSetup(
        team_id=1,
        formation_type="3-3",
        side=TeamSide.HOME,
        players=_home_setup().players,
    )
    with pytest.raises(MatchInitializationError):
        build_initial_state(MATCH_ID, TOTAL_TICKS, home, _away_setup())


def test_deberia_fallar_si_los_roles_no_corresponden_a_la_formacion():
    """3 titulares, pero con roles de la OTRA formación."""
    home = TeamMatchSetup(
        team_id=1,
        formation_type="2-1",
        side=TeamSide.HOME,
        players=[_starter(101, "DEFENDER"), _starter(102, "FORWARD_LEFT"), _starter(103, "FORWARD_RIGHT")]
        + [_substitute(104), _substitute(105), _substitute(106)],
    )
    with pytest.raises(MatchInitializationError):
        build_initial_state(MATCH_ID, TOTAL_TICKS, home, _away_setup())


def test_deberia_fallar_si_un_titular_no_tiene_rol():
    home = TeamMatchSetup(
        team_id=1,
        formation_type="2-1",
        side=TeamSide.HOME,
        players=[
            LineupPlayer(player_id=101, is_starter=True, role=None, behavior_id=1),
            _starter(102, "DEF_RIGHT"),
            _starter(103, "FORWARD"),
        ]
        + [_substitute(104), _substitute(105), _substitute(106)],
    )
    with pytest.raises(MatchInitializationError):
        build_initial_state(MATCH_ID, TOTAL_TICKS, home, _away_setup())


def test_deberia_fallar_si_un_suplente_tiene_rol_asignado():
    home = TeamMatchSetup(
        team_id=1,
        formation_type="2-1",
        side=TeamSide.HOME,
        players=[_starter(101, "DEF_LEFT"), _starter(102, "DEF_RIGHT"), _starter(103, "FORWARD")]
        + [LineupPlayer(player_id=104, is_starter=False, role="FORWARD", behavior_id=1), _substitute(105), _substitute(106)],
    )
    with pytest.raises(MatchInitializationError):
        build_initial_state(MATCH_ID, TOTAL_TICKS, home, _away_setup())


def test_deberia_fallar_si_falta_el_comportamiento_de_un_jugador():
    home = TeamMatchSetup(
        team_id=1,
        formation_type="2-1",
        side=TeamSide.HOME,
        players=[
            LineupPlayer(player_id=101, is_starter=True, role="DEF_LEFT", behavior_id=None),
            _starter(102, "DEF_RIGHT"),
            _starter(103, "FORWARD"),
        ]
        + [_substitute(104), _substitute(105), _substitute(106)],
    )
    with pytest.raises(MatchInitializationError):
        build_initial_state(MATCH_ID, TOTAL_TICKS, home, _away_setup())


def test_deberia_fallar_si_hay_un_jugador_repetido_en_la_alineacion():
    home = TeamMatchSetup(
        team_id=1,
        formation_type="2-1",
        side=TeamSide.HOME,
        players=[_starter(101, "DEF_LEFT"), _starter(101, "DEF_RIGHT"), _starter(103, "FORWARD")]
        + [_substitute(104), _substitute(105), _substitute(106)],
    )
    with pytest.raises(MatchInitializationError):
        build_initial_state(MATCH_ID, TOTAL_TICKS, home, _away_setup())


# --- Regresión: mutable defaults compartidos entre instancias ---


def test_deberia_dos_estados_no_compartir_el_diccionario_de_jugadores():
    """
    Regresión del bug clásico de Python: si MatchState.players tuviera
    `= {}` como default (en vez de field(default_factory=dict)), todas
    las instancias compartirían el MISMO diccionario.
    """
    estado_a = build_initial_state(1, TOTAL_TICKS, _home_setup(), _away_setup())
    estado_b = build_initial_state(2, TOTAL_TICKS, _home_setup(), _away_setup())

    assert estado_a.players is not estado_b.players

    estado_a.players[101].position = None  # modifico el jugador 101 de A

    assert estado_b.players[101].position is not None  # B no se entera


# --- MatchRegistry ---


def test_deberia_registry_devolver_none_si_no_existe_el_match():
    registry = MatchRegistry()
    assert registry.get(999) is None


def test_deberia_registry_guardar_y_devolver_el_mismo_estado():
    registry = MatchRegistry()
    state = build_initial_state(MATCH_ID, TOTAL_TICKS, _home_setup(), _away_setup())

    registry.add(state)

    assert registry.get(MATCH_ID) is state


def test_deberia_registry_fallar_si_se_agrega_el_mismo_match_id_dos_veces():
    registry = MatchRegistry()
    registry.add(build_initial_state(MATCH_ID, TOTAL_TICKS, _home_setup(), _away_setup()))

    with pytest.raises(ValueError):
        registry.add(build_initial_state(MATCH_ID, TOTAL_TICKS, _home_setup(), _away_setup()))


def test_deberia_registry_no_devolver_nada_tras_remove():
    registry = MatchRegistry()
    state = build_initial_state(MATCH_ID, TOTAL_TICKS, _home_setup(), _away_setup())
    registry.add(state)

    registry.remove(MATCH_ID)

    assert registry.get(MATCH_ID) is None


def test_deberia_dos_partidos_en_el_registry_no_compartir_estado():
    registry = MatchRegistry()
    registry.add(build_initial_state(1, TOTAL_TICKS, _home_setup(), _away_setup()))
    registry.add(build_initial_state(2, TOTAL_TICKS, _home_setup(), _away_setup()))

    registry.get(1).score.home = 5

    assert registry.get(2).score.home == 0
