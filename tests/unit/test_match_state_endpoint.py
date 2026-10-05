"""
Tests de GET /api/v1/matches/{match_id}/state.

La DB (SQLite en memoria) aporta partido, usuarios, equipos y jugadores; el
estado en vivo se arma con el motor real (build_initial_state) y se registra
en match_registry, igual que lo haría el lanzador del partido.
"""

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.security import create_access_token, create_ws_global_token
from src.database.base import Base, get_db
from src.engine.pitch import TeamSide
from src.engine.state import (
    LineupPlayer,
    MatchState,
    TeamMatchSetup,
    build_initial_state,
    match_registry,
)
from src.main import app
from src.models import Match, MatchStatus, Player, Team, User

TOTAL_TICKS = 240
ROLES_2_1 = ["DEF_LEFT", "DEF_RIGHT", "FORWARD"]
HOST_BEHAVIOR_BASE = 11  # los 6 del anfitrión usan 11..16
AWAY_BEHAVIOR_BASE = 21  # los 6 del visitante usan 21..26

# match_ids que cada test registró en el registry global (para limpiarlos)
_IDS_REGISTRADOS: list[int] = []


# --- Base, cliente y limpieza del registry ------

@pytest.fixture(autouse=True)
def _limpiar_registry():
    """match_registry es un singleton global: si un test deja un estado
    registrado, contamina al siguiente (cada test reinicia los match_id en 1)."""
    yield
    for match_id in _IDS_REGISTRADOS:
        match_registry.remove(match_id)
    _IDS_REGISTRADOS.clear()


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys_on(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def client(db):
    def override_get_db():
        s = sessionmaker(bind=db.get_bind(), autoflush=False)()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- Helpers ----

def _crear_usuario(db, n: int) -> User:
    user = User(
        username=f"user{n}", email=f"user{n}@example.com",
        password_hash="hash-falso", team=Team(team_name=f"Equipo {n}"),
    )
    db.add(user)
    db.commit()
    return user


def _crear_partido(db, host: User, away: User | None, status=MatchStatus.IN_PROGRESS) -> Match:
    match = Match(
        match_duration=2, status=status,
        team_host_id=host.team_id,
        team_away_id=away.team_id if away else None,
    )
    db.add(match)
    db.commit()
    return match


def _crear_jugadores(db, team_id: int) -> list[Player]:
    """6 jugadores del equipo. Cada atributo PACSS tiene un valor DISTINTO
    (suman 300) para detectar si la respuesta cruza un atributo con otro."""
    jugadores = [
        Player(
            team_id=team_id, name=f"Jugador {team_id}-{i}", number=i,
            power=40, agility=50, control=60, speed=70, strength=80,
        )
        for i in range(1, 7)
    ]
    db.add_all(jugadores)
    db.commit()
    return jugadores


def _setup(team_id: int, side: TeamSide, jugadores: list[Player], behavior_base: int) -> TeamMatchSetup:
    """Los 3 primeros son titulares (formación 2-1) y los 3 últimos suplentes.
    El behavior_id de cada uno es behavior_base + su posición (11, 12, ...)."""
    titulares = [
        LineupPlayer(player_id=j.player_id, is_starter=True, role=ROLES_2_1[i], behavior_id=behavior_base + i)
        for i, j in enumerate(jugadores[:3])
    ]
    suplentes = [
        LineupPlayer(player_id=j.player_id, is_starter=False, role=None, behavior_id=behavior_base + 3 + i)
        for i, j in enumerate(jugadores[3:])
    ]
    return TeamMatchSetup(team_id=team_id, formation_type="2-1", side=side, players=titulares + suplentes)


def _registrar_estado(match: Match, jugadores_host: list[Player], jugadores_away: list[Player]) -> MatchState:
    state = build_initial_state(
        match.match_id,
        TOTAL_TICKS,
        _setup(match.team_host_id, TeamSide.HOME, jugadores_host, HOST_BEHAVIOR_BASE),
        _setup(match.team_away_id, TeamSide.AWAY, jugadores_away, AWAY_BEHAVIOR_BASE),
    )
    match_registry.add(state)
    _IDS_REGISTRADOS.append(match.match_id)
    return state


@dataclass
class Escenario:
    host: User
    away: User
    match: Match
    jugadores_host: list[Player]
    jugadores_away: list[Player]
    state: MatchState


@pytest.fixture()
def partido_en_curso(db) -> Escenario:
    """Partido IN_PROGRESS en la DB, con sus 12 jugadores y su estado en memoria."""
    host, away = _crear_usuario(db, 1), _crear_usuario(db, 2)
    match = _crear_partido(db, host, away)
    jugadores_host = _crear_jugadores(db, host.team_id)
    jugadores_away = _crear_jugadores(db, away.team_id)
    state = _registrar_estado(match, jugadores_host, jugadores_away)
    return Escenario(host, away, match, jugadores_host, jugadores_away, state)


def _url(match_id) -> str:
    return f"/api/v1/matches/{match_id}/state"


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.user_id)}"}


def _ids(response) -> list[int]:
    return [p["player_id"] for p in response.json()["players"]]


# --- Autenticación (401) ----

def test_deberia_devolver_401_sin_token(client, partido_en_curso):
    response = client.get(_url(partido_en_curso.match.match_id))

    assert response.status_code == 401
    assert response.json()["error"] == "UNAUTHORIZED"


def test_deberia_devolver_401_si_el_token_no_es_de_login(client, partido_en_curso):
    headers = {"Authorization": f"Bearer {create_ws_global_token(partido_en_curso.host.user_id)}"}

    response = client.get(_url(partido_en_curso.match.match_id), headers=headers)

    assert response.status_code == 401


def test_deberia_devolver_401_si_el_usuario_del_token_ya_no_existe(client, partido_en_curso):
    headers = {"Authorization": f"Bearer {create_access_token(9999)}"}

    response = client.get(_url(partido_en_curso.match.match_id), headers=headers)

    assert response.status_code == 401
    assert response.json()["error"] == "UNAUTHORIZED"


# --- Orden de validación: 404 -> 403 -> 400 ----

def test_deberia_devolver_404_si_el_partido_no_existe(client, db):
    user = _crear_usuario(db, 1)

    response = client.get(_url(999), headers=_auth(user))

    assert response.status_code == 404
    # se chequea el código: el 404 por defecto de FastAPI (ruta inexistente) no lo trae
    assert response.json()["error"] == "MATCH_NOT_FOUND"


def test_deberia_devolver_403_si_el_equipo_no_participa(client, db, partido_en_curso):
    espectador = _crear_usuario(db, 3)

    response = client.get(_url(partido_en_curso.match.match_id), headers=_auth(espectador))

    assert response.status_code == 403
    assert response.json()["error"] == "UNAUTHORIZED_ACTION"


def test_deberia_devolver_400_match_pending_si_el_partido_no_inicio(client, db):
    host = _crear_usuario(db, 1)
    match = _crear_partido(db, host, None, MatchStatus.PENDING)

    response = client.get(_url(match.match_id), headers=_auth(host))

    assert response.status_code == 400
    assert response.json()["error"] == "MATCH_PENDING"


def test_deberia_devolver_400_match_finished_si_el_partido_termino(client, db):
    host, away = _crear_usuario(db, 1), _crear_usuario(db, 2)
    match = _crear_partido(db, host, away, MatchStatus.FINISHED)

    response = client.get(_url(match.match_id), headers=_auth(host))

    assert response.status_code == 400
    assert response.json()["error"] == "MATCH_FINISHED"


def test_deberia_devolver_403_y_no_400_si_es_un_partido_ajeno_finished(client, db):
    """Fija el orden del ticket: la participación se valida ANTES que el estado."""
    host, away, espectador = _crear_usuario(db, 1), _crear_usuario(db, 2), _crear_usuario(db, 3)
    match = _crear_partido(db, host, away, MatchStatus.FINISHED)

    response = client.get(_url(match.match_id), headers=_auth(espectador))

    assert response.status_code == 403
    assert response.json()["error"] == "UNAUTHORIZED_ACTION"


def test_deberia_devolver_403_y_no_400_si_es_un_partido_ajeno_pending(client, db):
    host, espectador = _crear_usuario(db, 1), _crear_usuario(db, 3)
    match = _crear_partido(db, host, None, MatchStatus.PENDING)

    response = client.get(_url(match.match_id), headers=_auth(espectador))

    assert response.status_code == 403
    assert response.json()["error"] == "UNAUTHORIZED_ACTION"


def test_deberia_devolver_422_si_el_match_id_no_es_numerico(client, db):
    user = _crear_usuario(db, 1)

    response = client.get(_url("abc"), headers=_auth(user))

    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"


# --- Caso feliz ----

def test_deberia_devolver_200_con_tick_total_marcador_y_6_jugadores(client, partido_en_curso):
    response = client.get(_url(partido_en_curso.match.match_id), headers=_auth(partido_en_curso.host))

    assert response.status_code == 200
    body = response.json()
    assert body["match_id"] == partido_en_curso.match.match_id
    assert body["current_tick"] == 0
    assert body["total_ticks"] == TOTAL_TICKS
    assert body["score"] == {"home": 0, "away": 0}
    assert len(body["players"]) == 6
    assert set(body["players"][0]) == {"player_id", "team_id", "name", "number", "attributes", "behavior_id"}


def test_deberia_reflejar_el_tick_y_el_marcador_del_estado_en_memoria(client, partido_en_curso):
    partido_en_curso.state.current_tick = 7
    partido_en_curso.state.score.home = 2
    partido_en_curso.state.score.away = 1

    body = client.get(_url(partido_en_curso.match.match_id), headers=_auth(partido_en_curso.host)).json()

    assert body["current_tick"] == 7
    assert body["score"] == {"home": 2, "away": 1}


def test_deberia_devolver_solo_a_los_titulares_y_no_a_los_suplentes(client, partido_en_curso):
    e = partido_en_curso
    titulares = {j.player_id for j in e.jugadores_host[:3] + e.jugadores_away[:3]}

    response = client.get(_url(e.match.match_id), headers=_auth(e.host))

    assert set(_ids(response)) == titulares


def test_deberia_mostrar_behavior_id_solo_de_los_propios_siendo_anfitrion(client, partido_en_curso):
    e = partido_en_curso

    players = client.get(_url(e.match.match_id), headers=_auth(e.host)).json()["players"]

    propios = {p["player_id"]: p["behavior_id"] for p in players if p["team_id"] == e.host.team_id}
    rivales = [p for p in players if p["team_id"] == e.away.team_id]
    assert propios == {j.player_id: HOST_BEHAVIOR_BASE + i for i, j in enumerate(e.jugadores_host[:3])}
    # la clave tiene que venir en el JSON, con valor null (no omitida)
    assert len(rivales) == 3
    assert all("behavior_id" in p and p["behavior_id"] is None for p in rivales)


def test_deberia_mostrar_behavior_id_solo_de_los_propios_siendo_visitante(client, partido_en_curso):
    e = partido_en_curso

    players = client.get(_url(e.match.match_id), headers=_auth(e.away)).json()["players"]

    propios = {p["player_id"]: p["behavior_id"] for p in players if p["team_id"] == e.away.team_id}
    rivales = [p for p in players if p["team_id"] == e.host.team_id]
    assert propios == {j.player_id: AWAY_BEHAVIOR_BASE + i for i, j in enumerate(e.jugadores_away[:3])}
    assert len(rivales) == 3
    assert all(p["behavior_id"] is None for p in rivales)


def test_deberia_no_modificar_el_estado_interno_al_filtrar_el_behavior_id(client, partido_en_curso):
    e = partido_en_curso
    rival = e.jugadores_away[0]

    client.get(_url(e.match.match_id), headers=_auth(e.host))

    # el filtro se aplica solo en la respuesta: el estado del motor conserva el real
    assert e.state.players[rival.player_id].behavior_id == AWAY_BEHAVIOR_BASE
    assert len(e.state.players) == 12


def test_deberia_traer_name_number_y_atributos_de_la_db(client, partido_en_curso):
    e = partido_en_curso
    jugador = e.jugadores_host[0]

    players = client.get(_url(e.match.match_id), headers=_auth(e.host)).json()["players"]

    p = next(p for p in players if p["player_id"] == jugador.player_id)
    assert p["team_id"] == e.host.team_id
    assert p["name"] == jugador.name
    assert p["number"] == jugador.number
    assert p["attributes"] == {"power": 40, "agility": 50, "control": 60, "speed": 70, "strength": 80}


def test_deberia_devolver_los_jugadores_ordenados_por_equipo_y_player_id(client, partido_en_curso):
    players = client.get(
        _url(partido_en_curso.match.match_id), headers=_auth(partido_en_curso.host)
    ).json()["players"]

    claves = [(p["team_id"], p["player_id"]) for p in players]
    assert claves == sorted(claves)


# --- Estado en memoria inconsistente ----

def test_deberia_devolver_404_si_el_partido_esta_in_progress_pero_no_hay_estado_en_memoria(client, db):
    host, away = _crear_usuario(db, 1), _crear_usuario(db, 2)
    match = _crear_partido(db, host, away)  # IN_PROGRESS, pero nadie registró el estado

    response = client.get(_url(match.match_id), headers=_auth(host))

    assert response.status_code == 404
    assert response.json()["error"] == "MATCH_NOT_FOUND"


def test_deberia_devolver_500_si_un_jugador_del_estado_no_existe_en_la_db(client, db, partido_en_curso):
    e = partido_en_curso
    db.delete(e.jugadores_away[0])  # sigue en el estado en memoria, pero ya no en la DB
    db.commit()
    # el client de la fixture re-lanza las excepciones del servidor; acá queremos ver el 500
    client_500 = TestClient(app, raise_server_exceptions=False)

    response = client_500.get(_url(e.match.match_id), headers=_auth(e.host))

    assert response.status_code == 500