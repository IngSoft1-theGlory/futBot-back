"""
Tests de GET /api/v1/matches/{match_id}/state, uno o dos por criterio de aceptacion.

La base (SQLite en memoria, fixture `session` de conftest) aporta partido, usuarios y
jugadores. El estado en vivo se arma A MANO (MatchState) y se registra en match_registry:
asi los tests no dependen de build_initial_state ni de como se arme la alineacion.
"""

import pytest
from fastapi.testclient import TestClient

from src.core.security import create_access_token
from src.database.base import get_db
from src.engine._01_to_world.pitch import TeamSide
from src.engine._01_to_world.data_types import Point2D, Vector2D
from src.engine._02_to_match.state import (
    BallState,
    MatchPhase,
    MatchPlayerState,
    MatchState,
    Score,
    match_registry,
)
from src.main import app
from src.models import Match, MatchStatus, Player, Team, User

MATCH_ID = 1


# --- Ayudas ---

def crear_usuario(session, n):
    user = User(
        username=f"user{n}", email=f"user{n}@example.com",
        password_hash="hash-falso", team=Team(team_name=f"Equipo {n}"),
    )
    session.add(user)
    session.commit()
    return user


def crear_partido(session, host, away, status=MatchStatus.IN_PROGRESS):
    match = Match(
        match_duration=2, status=status,
        team_host_id=host.team_id,
        team_away_id=away.team_id if away else None,
    )
    session.add(match)
    session.commit()
    return match


def crear_jugadores(session, team_id):
    """6 jugadores del equipo; cada atributo tiene un valor distinto para detectar cruces."""
    jugadores = [
        Player(team_id=team_id, name=f"Jugador {team_id}-{i}", number=i,
               power=40, agility=50, control=60, speed=70, strength=80)
        for i in range(1, 7)
    ]
    session.add_all(jugadores)
    session.commit()
    return jugadores


def estado_en_memoria(match, jugadores_host, jugadores_away):
    """
    MatchState armado a mano: de cada equipo, los 3 primeros estan en cancha y los
    3 ultimos son suplentes (position=None). El behavior_id del host es 11, 12, ...
    y el del visitante 21, 22, ...
    """
    players = {}
    for side, team_id, jugadores, base in (
        (TeamSide.HOME, match.team_host_id, jugadores_host, 11),
        (TeamSide.AWAY, match.team_away_id, jugadores_away, 21),
    ):
        for i, jugador in enumerate(jugadores):
            titular = i < 3
            players[jugador.player_id] = MatchPlayerState(
                player_id=jugador.player_id, team_id=team_id, side=side,
                is_starter=titular, role=None, behavior_id=base + i,
                position=Point2D(10.0 + i, 30.0) if titular else None,
            )
    state = MatchState(
        match_id=match.match_id, phase=MatchPhase.IN_PROGRESS, current_tick=0,
        total_ticks=240, score=Score(),
        ball=BallState(Point2D(52.5, 30.0), Vector2D(0.0, 0.0)), players=players,
    )
    match_registry.add(state)
    return state


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.user_id)}"}


def url(match_id):
    return f"/api/v1/matches/{match_id}/state"


@pytest.fixture()
def client(session):
    app.dependency_overrides[get_db] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def partido(session):
    """Partido IN_PROGRESS con sus 12 jugadores y su estado en memoria."""
    host, away = crear_usuario(session, 1), crear_usuario(session, 2)
    match = crear_partido(session, host, away)
    jugadores_host = crear_jugadores(session, host.team_id)
    jugadores_away = crear_jugadores(session, away.team_id)
    state = estado_en_memoria(match, jugadores_host, jugadores_away)
    yield {"host": host, "away": away, "match": match, "state": state,
           "jugadores_host": jugadores_host, "jugadores_away": jugadores_away}
    match_registry.remove(match.match_id)   # el registry es global: lo dejo limpio


# --- 200 - forma de la respuesta y jugadores en cancha ---

def test_deberia_devolver_200_con_el_estado_y_solo_los_6_jugadores_en_cancha(client, partido):
    state = partido["state"]
    state.current_tick = 7
    state.score.home = 2
    state.score.away = 1

    response = client.get(url(partido["match"].match_id), headers=auth(partido["host"]))

    assert response.status_code == 200
    body = response.json()
    assert body["match_id"] == partido["match"].match_id
    assert body["current_tick"] == 7
    assert body["total_ticks"] == 240
    assert body["score"] == {"home": 2, "away": 1}
    # 3 titulares por equipo: los suplentes (position=None) no aparecen
    en_cancha = {j.player_id for j in partido["jugadores_host"][:3] + partido["jugadores_away"][:3]}
    assert {p["player_id"] for p in body["players"]} == en_cancha


def test_deberia_traer_name_number_y_atributos_de_la_base(client, partido):
    body = client.get(url(partido["match"].match_id), headers=auth(partido["host"])).json()

    jugador = body["players"][0]
    assert set(jugador) == {"player_id", "team_id", "name", "number", "attributes", "behavior_id"}
    assert jugador["name"].startswith("Jugador ")
    assert jugador["attributes"] == {"power": 40, "agility": 50, "control": 60, "speed": 70, "strength": 80}


# --- behavior_id - real el propio, null el rival ---

@pytest.mark.parametrize("quien, team, propio, rival", [
    ("host", "host", 11, 21),   # consulta el anfitrion: ve 11..13 y no ve 21..23
    ("away", "away", 21, 11),   # consulta el visitante: al reves
])
def test_deberia_mostrar_behavior_id_solo_de_los_propios(client, partido, quien, team, propio, rival):
    usuario = partido[quien]

    body = client.get(url(partido["match"].match_id), headers=auth(usuario)).json()

    propios = [p["behavior_id"] for p in body["players"] if p["team_id"] == usuario.team_id]
    rivales = [p["behavior_id"] for p in body["players"] if p["team_id"] != usuario.team_id]
    assert propios == [propio, propio + 1, propio + 2]
    assert rivales == [None, None, None]


def test_deberia_dejar_intacto_el_behavior_id_del_estado_en_memoria(client, partido):
    antes = {pid: p.behavior_id for pid, p in partido["state"].players.items()}

    client.get(url(partido["match"].match_id), headers=auth(partido["host"]))

    despues = {pid: p.behavior_id for pid, p in partido["state"].players.items()}
    assert despues == antes   # el filtro se aplica en la respuesta, no en el estado


# --- substitutes - suplentes del propio equipo ---

def test_deberia_devolver_en_substitutes_los_suplentes_del_equipo_del_usuario(client, partido):
    body = client.get(url(partido["match"].match_id), headers=auth(partido["host"])).json()

    suplentes_host = {j.player_id for j in partido["jugadores_host"][3:]}
    assert {p["player_id"] for p in body["substitutes"]} == suplentes_host


def test_deberia_no_incluir_los_suplentes_del_rival(client, partido):
    body = client.get(url(partido["match"].match_id), headers=auth(partido["host"])).json()

    suplentes_rival = {j.player_id for j in partido["jugadores_away"][3:]}
    assert suplentes_rival.isdisjoint({p["player_id"] for p in body["substitutes"]})


def test_deberia_pasar_al_que_salio_a_substitutes_y_al_que_entro_a_players(client, partido):
    state = partido["state"]
    sale, entra = partido["jugadores_host"][0], partido["jugadores_host"][3]
    # sustitucion hecha a mano: el que entra toma la posicion del que sale
    state.players[entra.player_id].position = state.players[sale.player_id].position
    state.players[sale.player_id].position = None

    body = client.get(url(partido["match"].match_id), headers=auth(partido["host"])).json()

    en_cancha = {p["player_id"] for p in body["players"]}
    suplentes = {p["player_id"] for p in body["substitutes"]}
    assert entra.player_id in en_cancha and entra.player_id not in suplentes
    assert sale.player_id in suplentes and sale.player_id not in en_cancha


# --- Errores ---

def test_deberia_devolver_401_sin_token_valido(client, partido):
    sin_token = client.get(url(partido["match"].match_id))
    usuario_inexistente = client.get(
        url(partido["match"].match_id),
        headers={"Authorization": f"Bearer {create_access_token(9999)}"},
    )

    for response in (sin_token, usuario_inexistente):
        assert response.status_code == 401
        assert response.json()["error"] == "UNAUTHORIZED"


def test_deberia_devolver_404_si_el_partido_no_existe(client, session):
    usuario = crear_usuario(session, 1)

    response = client.get(url(999), headers=auth(usuario))

    assert response.status_code == 404
    assert response.json()["error"] == "MATCH_NOT_FOUND"


def test_deberia_devolver_403_si_el_equipo_no_participa(client, session, partido):
    espectador = crear_usuario(session, 3)

    response = client.get(url(partido["match"].match_id), headers=auth(espectador))

    assert response.status_code == 403
    assert response.json()["error"] == "UNAUTHORIZED_ACTION"


@pytest.mark.parametrize("status, error", [
    (MatchStatus.PENDING, "MATCH_PENDING"),
    (MatchStatus.FINISHED, "MATCH_FINISHED"),
])
def test_deberia_devolver_400_si_el_partido_no_esta_en_curso(client, session, status, error):
    host, away = crear_usuario(session, 1), crear_usuario(session, 2)
    match = crear_partido(session, host, away if status == MatchStatus.FINISHED else None, status)

    response = client.get(url(match.match_id), headers=auth(host))

    assert response.status_code == 400
    assert response.json()["error"] == error


def test_deberia_devolver_404_si_esta_en_curso_pero_no_hay_estado_en_memoria(client, session):
    host, away = crear_usuario(session, 1), crear_usuario(session, 2)
    match = crear_partido(session, host, away)   # IN_PROGRESS, nadie registro el estado

    response = client.get(url(match.match_id), headers=auth(host))

    assert response.status_code == 404
    assert response.json()["error"] == "MATCH_NOT_FOUND"