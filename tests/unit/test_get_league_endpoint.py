"""
Tests HTTP para GET /api/v1/leagues/{leagueId}

Pasan por HTTP de verdad (TestClient): ruta + service + repository + base juntos.
Como todavia no existe el endpoint de unirse a liga en develop, los equipos
inscriptos se insertan directo en lineup_entries.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.core.security import create_access_token
from src.database.base import get_db
from src.main import app
from src.models import Behavior, League, LeagueStatus, LineupEntry, Player, Team, User
from src.services.fixture_service import generate_fixture

URL = "/api/v1/leagues"


#  Fixtures

@pytest.fixture()
def client(session):
    app.dependency_overrides[get_db] = lambda: session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(usuario_con_equipo):
    token = create_access_token(user_id=usuario_con_equipo.user_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def otro_usuario(session):
    team = Team(team_name="Rival FC")
    user = User(
        username="rival", email="rival@example.com",
        password_hash="hash-falso-de-prueba", team=team,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture()
def otro_auth_headers(otro_usuario):
    token = create_access_token(user_id=otro_usuario.user_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def comportamiento(session):
    behavior = Behavior(
        name="Patear", description="Patea la pelota",
        code="def on_tick(api): pass", is_default=True,
    )
    session.add(behavior)
    session.commit()
    return behavior


# Helpers

def _crear_liga(session, host_team, nombre="Liga", status=LeagueStatus.PENDING, password_hash=None):
    liga = League(
        league_name=nombre, max_teams=8, status=status,
        password_hash=password_hash, match_duration=5,
        host_team_id=host_team.team_id,
    )
    session.add(liga)
    session.commit()
    return liga


def _inscribir(session, liga, equipo, comportamiento):
    """6 filas en lineup_entries (3 titulares y 3 suplentes), como el POST de unirse."""
    roles = ["DEF_LEFT", "DEF_RIGHT", "FORWARD", None, None, None]
    for numero, role in enumerate(roles, start=1):
        jugador = Player(
            team_id=equipo.team_id, name=f"J{numero}", number=numero,
            power=60, agility=60, control=60, speed=60, strength=60,
        )
        session.add(jugador)
        session.flush()
        session.add(LineupEntry(
            league_id=liga.league_id, team_id=equipo.team_id,
            player_id=jugador.player_id, behavior_id=comportamiento.behavior_id,
            role=role, is_starter=role is not None,
        ))
    session.commit()


def _liga_con_host(session, host, comportamiento, **kwargs):
    liga = _crear_liga(session, host.team, **kwargs)
    _inscribir(session, liga, host.team, comportamiento)
    return liga


# Casos exitosos

def test_deberia_devolver_el_detalle_completo_de_una_liga_publica(
    client, session, usuario_con_equipo, comportamiento, auth_headers
):
    liga = _liga_con_host(session, usuario_con_equipo, comportamiento, nombre="Apertura")

    response = client.get(f"{URL}/{liga.league_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {
        "league_id": liga.league_id,
        "league_name": "Apertura",
        "status": "PENDING",
        "is_private": False,
        "host_team_id": usuario_con_equipo.team_id,
        "max_teams": 8,
        "current_teams_count": 1,
        "match_duration": 5,
        "teams": [{"team_id": usuario_con_equipo.team_id, "team_name": "Sacachispas FC"}],
        "ranking": [],
        "fixture": [],
    }


def test_deberia_listar_equipos_sin_duplicados_con_el_anfitrion_primero(
    client, session, usuario_con_equipo, otro_usuario, comportamiento, auth_headers
):
    # el rival tiene un team_id mayor, pero se inscribe primero el host igual que en el flujo real
    liga = _liga_con_host(session, usuario_con_equipo, comportamiento)
    _inscribir(session, liga, otro_usuario.team, comportamiento)

    data = client.get(f"{URL}/{liga.league_id}", headers=auth_headers).json()

    assert [t["team_id"] for t in data["teams"]] == [usuario_con_equipo.team_id, otro_usuario.team_id]
    assert data["current_teams_count"] == 2


def test_deberia_mostrar_una_liga_publica_a_un_usuario_no_inscripto(
    client, session, usuario_con_equipo, comportamiento, otro_auth_headers
):
    liga = _liga_con_host(session, usuario_con_equipo, comportamiento)

    response = client.get(f"{URL}/{liga.league_id}", headers=otro_auth_headers)

    assert response.status_code == 200


def test_deberia_mostrar_una_liga_privada_a_un_equipo_inscripto(
    client, session, usuario_con_equipo, otro_usuario, comportamiento, otro_auth_headers
):
    liga = _liga_con_host(session, usuario_con_equipo, comportamiento, password_hash="hash-secreto-123")
    _inscribir(session, liga, otro_usuario.team, comportamiento)

    response = client.get(f"{URL}/{liga.league_id}", headers=otro_auth_headers)

    assert response.status_code == 200
    assert response.json()["is_private"] is True
    assert "hash-secreto-123" not in response.text


def test_deberia_devolver_una_liga_iniciada_con_el_mismo_formato(
    client, session, usuario_con_equipo, comportamiento, auth_headers
):
    liga = _liga_con_host(session, usuario_con_equipo, comportamiento, status=LeagueStatus.IN_PROGRESS)

    data = client.get(f"{URL}/{liga.league_id}", headers=auth_headers).json()

    assert data["status"] == "IN_PROGRESS"
    assert data["ranking"] == [] and data["fixture"] == []


# Errores

def test_deberia_responder_403_si_la_liga_es_privada_y_no_esta_inscripto(
    client, session, usuario_con_equipo, comportamiento, otro_auth_headers
):
    liga = _liga_con_host(session, usuario_con_equipo, comportamiento, password_hash="hash-secreto-123")

    response = client.get(f"{URL}/{liga.league_id}", headers=otro_auth_headers)

    assert response.status_code == 403
    assert response.json()["error"] == "UNAUTHORIZED_ACTION"


def test_deberia_responder_404_si_la_liga_no_existe(client, auth_headers):
    response = client.get(f"{URL}/9999", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["error"] == "LEAGUE_NOT_FOUND"


def test_deberia_responder_401_sin_token(client, session, usuario_con_equipo, comportamiento):
    liga = _liga_con_host(session, usuario_con_equipo, comportamiento)

    response = client.get(f"{URL}/{liga.league_id}")

    assert response.status_code == 401
    assert response.json()["error"] == "UNAUTHORIZED"


def test_deberia_responder_422_si_el_id_no_es_un_entero(client, auth_headers):
    response = client.get(f"{URL}/abc", headers=auth_headers)

    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"


def test_deberia_devolver_el_fixture_ordenado_por_fecha_con_los_datos_de_los_equipos(
    client, session, usuario_con_equipo, otro_usuario, comportamiento, auth_headers
):
    # Crea cuatro equipos para comprobar el fixture completo
    equipos = [
        usuario_con_equipo.team, 
        otro_usuario.team, 
        Team(team_name="Tercero FC"), 
        Team(team_name="Cuarto FC")
    ]

    # Guarda los dos equipos creados directamente en este test
    session.add_all(equipos[2:])
    session.commit()
    # Crea una liga activa y registra los cuatro equipos
    liga = _crear_liga(session, usuario_con_equipo.team, status=LeagueStatus.IN_PROGRESS)
    for equipo in equipos:
        _inscribir(session, liga, equipo, comportamiento)

    # Genera y guarda los partidos de la liga
    generate_fixture(session, liga)
    session.commit()

    # Consulta el endpoint y obtiene el fixture de la respuesta
    fixture = client.get(f"{URL}/{liga.league_id}", headers=auth_headers).json()["fixture"]

    # Crea un diccionario para buscar el nombre de cada equipo por su ID
    nombres = {e.team_id: e.team_name for e in equipos}

    # Extrae las fechas para comprobar su orden y cantidad.
    fechas = [p["round_number"] for p in fixture]

    # Cuatro equipos generan seis partidos distribuidos en tres fechas
    assert len(fixture) == 6
    assert fechas == sorted(fechas)          # ordenado por fecha
    assert set(fechas) == {1, 2, 3}
    for partido in fixture:
        # Todos los partidos recién creados comienzan pendientes y sin goles
        assert partido["status"] == "PENDING"
        assert partido["score"] == {"home": 0, "away": 0}
        # La respuesta debe incluir el nombre correcto de cada equipo
        assert partido["team_host"]["team_name"] == nombres[partido["team_host"]["team_id"]]
        assert partido["team_away"]["team_name"] == nombres[partido["team_away"]["team_id"]]