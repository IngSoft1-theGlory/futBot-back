"""Tests del snapshot por jugador: build_player_snapshot + getters de PlayerAPI."""

import copy
from dataclasses import FrozenInstanceError

import pytest
from src.engine.state import MatchPlayerState, MatchState, MatchPhase, Score, BallState
from src.engine._01_to_world.pitch import TeamSide, goal_center, opponent_goal_center
from src.engine._01_to_world.data_types import Point2D, Vector2D, AttributeType
from src.engine.player_api import PlayerAPI
from src.engine.snapshot import build_player_snapshot


# --- Helpers: arman el escenario de prueba (no son tests, por eso empiezan con _) ---

def _player(player_id, team_id, side, x, starter=True):
    """Crea un jugador con lo mínimo que el builder necesita leer."""
    return MatchPlayerState(
        player_id=player_id,
        team_id=team_id,
        side=side,
        is_starter=starter,
        role=None,  # el builder no usa el rol, así que no importa
        behavior_id=1,  # idem
        # Titular: está en cancha, con una x distinta para poder distinguirlo.
        # Suplente: position=None, que es como el motor marca "está en el banco".
        position=Point2D(x, 10.0) if starter else None,
        # Truco: cada atributo vale el player_id. Así, si get_attribute
        # devuelve 101 sabemos que vino del jugador 101 y no de otro.
        attributes={a: player_id for a in AttributeType},
    )


def _state():
    """
    Arma un MatchState a mano: 3 titulares + 1 suplente por equipo.
    Cada test llama a _state() y obtiene un estado nuevo, asi que un test
    que mute el estado no puede contaminar a los demás.
    """
    jugadores = [
        _player(101, 1, TeamSide.HOME, 10), _player(102, 1, TeamSide.HOME, 20),
        _player(103, 1, TeamSide.HOME, 30), _player(104, 1, TeamSide.HOME, 0, starter=False),
        _player(201, 2, TeamSide.AWAY, 70), _player(202, 2, TeamSide.AWAY, 80),
        _player(203, 2, TeamSide.AWAY, 90), _player(204, 2, TeamSide.AWAY, 0, starter=False),
    ]
    return MatchState(
        match_id=1,
        phase=MatchPhase.IN_PROGRESS,
        current_tick=0,
        total_ticks=240,
        score=Score(),
        ball=BallState(Point2D(52.5, 30.0), Vector2D(0.0, 0.0)),

        # el estado guarda los jugadores en un dict {player_id: jugador}
        players={p.player_id: p for p in jugadores},
    )


def _api(state, player_id):
    """
    Arma el PlayerAPI de un jugador, igual que lo haría el motor en un tick.
    """
    game_state, attributes = build_player_snapshot(state, player_id)
    return PlayerAPI(game_state, attributes)


def test_deberia_devolver_posicion_pelota_y_arcos_del_jugador():
    state = _state()
    gs = _api(state, 201).get_game_state()  # 201 es AWAY

    assert gs.my_position == state.players[201].position
    assert gs.ball_position == state.ball.position
    assert gs.team_goal == goal_center(TeamSide.AWAY)
    assert gs.opponent_goal == opponent_goal_center(TeamSide.AWAY)


def test_deberia_ser_inmutable():
    gs = _api(_state(), 101).get_game_state()
    # frozen=True hace que reasignar un atributo lance FrozenInstanceError.
    with pytest.raises(FrozenInstanceError):
        gs.my_position = Point2D(0, 0) 


def test_deberia_tener_2_teammates_y_3_opponents():
    gs = _api(_state(), 101).get_game_state()

    assert len(gs.teammates) == 2
    assert len(gs.opponents) == 3


def test_deberia_excluir_al_propio_jugador_de_los_teammates():
    state = _state()
    gs = _api(state, 101).get_game_state()

    assert state.players[101].position not in gs.teammates


def test_deberia_no_mezclar_teammates_y_opponents():
    state = _state()
    gs = _api(state, 101).get_game_state()

    for pid in (102, 103):  # compañeros de 101
        assert state.players[pid].position in gs.teammates
        assert state.players[pid].position not in gs.opponents
    for pid in (201, 202, 203):  # rivales de 101
        assert state.players[pid].position in gs.opponents
        assert state.players[pid].position not in gs.teammates


# AC dos jugadores en el mismo tick reciben GameState distintos 
def test_deberia_dar_game_state_distintos_a_dos_jugadores():
    state = _state()
    gs_a = _api(state, 101).get_game_state()
    gs_b = _api(state, 102).get_game_state()

    # Cada uno conserva lo suyo, por lo tanto los GameState completos son distintos.
    assert gs_a.my_position == state.players[101].position
    assert gs_b.my_position == state.players[102].position
   
    assert gs_a != gs_b


# AC mutar las listas no afecta a otro jugador ni al motor 
def test_deberia_mutar_las_listas_no_alterar_a_otro_jugador_ni_al_motor():
    state = _state()

    antes = copy.deepcopy(state)
    gs_a = _api(state, 101).get_game_state()
    gs_b = _api(state, 102).get_game_state()

    # simulo un comportamiento feo que ensucia la lista
    gs_a.teammates.append(Point2D(0, 0))
    gs_a.opponents.clear()

    # el otro jugador y el motor no se enteran 
    assert len(gs_b.teammates) == 2
    assert len(gs_b.opponents) == 3

    assert state == antes # esto compara el estado completo campo por campo. Si el builder hubiera pasado listas internas del motor sin copiar, esto fallaria


def test_deberia_get_attribute_devolver_lo_guardado_para_los_cinco_atributos():
    state = _state()
    api_a, api_b = _api(state, 101), _api(state, 201)

    # recorrer AttributeType cubre los cinco atributos sin escribirlos a mano.
    # como cada atributo vale el player_id, tambien se verifica que cada
    # API devuelve los datos de su jugador y no los del otro.
    for attr in AttributeType:
        assert api_a.get_attribute(attr) == 101
        assert api_b.get_attribute(attr) == 201


def test_deberia_get_reach_distance_ser_estrictamente_creciente():
    state = _state()

    state.players[101].attributes[AttributeType.CONTROL] = 20
    state.players[102].attributes[AttributeType.CONTROL] = 60
    state.players[201].attributes[AttributeType.CONTROL] = 100

    low = _api(state, 101).get_reach_distance()
    mid = _api(state, 102).get_reach_distance()
    high = _api(state, 201).get_reach_distance()

    assert low < mid < high


def test_deberia_llamar_a_los_getters_dejar_el_estado_identico():
    state = _state()
    antes = copy.deepcopy(state) # copia del estado antes de llamar a los getters
    api = _api(state, 101)

    api.get_game_state()
    api.get_attribute(AttributeType.POWER)
    api.get_reach_distance()

    # un getter es una consulta, leer no debe cambiar nada. si alguno
    # modificara el estado sin querer, esta comparación fallaria
    assert state == antes