"""
Tests de las rutas de iniciar liga: que publiquen los eventos correctos.
La logica (validaciones, fixture) se prueba en test_start_league_service.py,
por eso aca el service y el event_bus estan reemplazados por mocks.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest
from fastapi.testclient import TestClient

from src.core.security import get_current_user
from src.database.base import get_db
from src.main import app
from src.models import League, LeagueStatus

URL = "/api/v1/leagues/7"

# Eventos que la ruta debe publicar para la liga 7 y el equipo 1
EVENTO_UNIDO = call("TEAM_JOINED_LEAGUE", {"league_id": 7, "team_id": 1})

EVENTO_INICIADA = call("LEAGUE_INITIATED", {
    "league_id": 7, "league_name": "Liga test", "max_teams": 4, "status": "IN_PROGRESS",
})

# Body valido para unirse a una liga
BODY_UNIRSE = {
    "team_id": 1,
    "formation_type": "2-1",
    "starting_players": [
        {"player_id": 1, "role": "DEF_LEFT", "behavior_id": 1},
        {"player_id": 2, "role": "DEF_RIGHT", "behavior_id": 1},
        {"player_id": 3, "role": "FORWARD", "behavior_id": 1},
    ],
    "substitute_players": [
        {"player_id": 4, "behavior_id": 1},
        {"player_id": 5, "behavior_id": 1},
        {"player_id": 6, "behavior_id": 1},
    ],
}


@pytest.fixture()
def client():
    """Cliente de prueba con usuario logueado y sin base de datos"""
    app.dependency_overrides[get_current_user] = lambda: 1  # la ruta cree que el usuario 1 inicio sesion
    app.dependency_overrides[get_db] = lambda: None         # no se usa la base: el service esta reemplazado
    yield TestClient(app)                                   # al terminar el test se limpia la cache de dependencias
    app.dependency_overrides.clear()  


@pytest.fixture()
def bus(monkeypatch):
    """Event bus falso: anota cada evento que publica la ruta"""
    mock = MagicMock()
    monkeypatch.setattr("src.routes.leagues.event_bus", mock)
    return mock


def liga_falsa(status):
    return League(league_id=7, league_name="Liga test", max_teams=4, status=status)


@pytest.fixture()
def start_league_falso(monkeypatch):
    """start_league falso: devuelve la liga ya iniciada"""
    monkeypatch.setattr("src.routes.leagues.start_league", lambda *args: liga_falsa(LeagueStatus.IN_PROGRESS))


@pytest.fixture()
def join_que_completa_el_cupo(monkeypatch):
    """join_league falso: el equipo completa el cupo, asi que la liga queda iniciada"""
    monkeypatch.setattr("src.routes.leagues.join_league", lambda *args: liga_falsa(LeagueStatus.IN_PROGRESS))


@pytest.fixture()
def join_que_no_completa_el_cupo(monkeypatch):
    """join_league falso: el equipo se une pero la liga sigue pendiente"""
    monkeypatch.setattr("src.routes.leagues.join_league", lambda *args: liga_falsa(LeagueStatus.PENDING))


def iniciar_liga(client):
    return client.put(URL, json={"status": "IN_PROGRESS"})


def unirse_a_la_liga(client):
    return client.post(f"{URL}/teams", json=BODY_UNIRSE)


def test_deberia_responder_200_y_publicar_league_initiated_una_sola_vez(client, bus, start_league_falso):
    respuesta = iniciar_liga(client)

    assert respuesta.status_code == 200
    assert respuesta.json() == {"league_id": 7, "league_name": "Liga test", "status": "IN_PROGRESS"}
    # se revisa que se haya publicado el evento LEAGUE_INITIATED una sola vez, y con los datos correctos
    assert bus.publish.call_args_list == [EVENTO_INICIADA]


def test_deberia_publicar_team_joined_y_luego_league_initiated_si_se_completa_el_cupo(
    client, bus, join_que_completa_el_cupo
):
    respuesta = unirse_a_la_liga(client)

    assert respuesta.status_code == 201
    assert bus.publish.call_args_list == [EVENTO_UNIDO, EVENTO_INICIADA]  # en ese orden


def test_deberia_publicar_solo_team_joined_si_no_se_completa_el_cupo(
    client, bus, join_que_no_completa_el_cupo
):
    respuesta = unirse_a_la_liga(client)

    assert respuesta.status_code == 201
    assert bus.publish.call_args_list == [EVENTO_UNIDO]