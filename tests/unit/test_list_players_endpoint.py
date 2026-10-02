"""
Tests HTTP para GET /api/v1/players
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from src.core.security import create_access_token
from src.database.base import get_db
from src.main import app
from src.models import Player, Team, User

URL = "/api/v1/players"


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


def _add_players(session, team_id, numbers):
    for n in numbers:
        session.add(Player(team_id=team_id, name=f"J{n}", number=n,
                           power=60, agility=60, control=60, speed=60, strength=60))
    session.commit()


def test_deberia_devolver_200_con_los_jugadores_y_paginacion_por_defecto(
    client, session, usuario_con_equipo, auth_headers
):
    _add_players(session, usuario_con_equipo.team_id, range(1, 26))

    response = client.get(URL, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 20
    assert set(body["data"][0].keys()) == {"player_id", "name", "number"}
    assert body["pagination"] == {
        "current_page": 1, "per_page": 20, "total_items": 25, "total_pages": 2,
    }


def test_deberia_respetar_page_y_limit_y_ordenar_por_numero(
    client, session, usuario_con_equipo, auth_headers
):
    # insertados en desorden para verificar que el orden sale del ORDER BY
    _add_players(session, usuario_con_equipo.team_id, [5, 1, 4, 2, 3])

    r1 = client.get(URL, params={"page": 1, "limit": 2}, headers=auth_headers).json()
    r2 = client.get(URL, params={"page": 2, "limit": 2}, headers=auth_headers).json()
    r3 = client.get(URL, params={"page": 3, "limit": 2}, headers=auth_headers).json()

    assert [p["number"] for p in r1["data"]] == [1, 2]
    assert [p["number"] for p in r2["data"]] == [3, 4]
    assert [p["number"] for p in r3["data"]] == [5]
    assert r1["pagination"]["total_pages"] == 3
    assert client.get(URL, params={"page": 1, "limit": 2}, headers=auth_headers).json() == r1


def test_no_deberia_devolver_jugadores_de_otros_equipos(
    client, session, usuario_con_equipo, auth_headers
):
    otro = Team(team_name="Otro FC")
    session.add(otro)
    session.commit()
    _add_players(session, otro.team_id, [1, 2, 3])
    _add_players(session, usuario_con_equipo.team_id, [10])

    body = client.get(URL, headers=auth_headers).json()

    assert [p["number"] for p in body["data"]] == [10]
    assert body["pagination"]["total_items"] == 1


def test_deberia_devolver_200_con_lista_vacia_si_no_hay_jugadores(client, auth_headers):
    response = client.get(URL, headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {
        "data": [],
        "pagination": {"current_page": 1, "per_page": 20, "total_items": 0, "total_pages": 0},
    }


def test_deberia_devolver_200_vacio_si_la_pagina_supera_total_pages(
    client, session, usuario_con_equipo, auth_headers
):
    _add_players(session, usuario_con_equipo.team_id, [1, 2, 3])

    response = client.get(URL, params={"page": 5}, headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["data"] == []
    assert response.json()["pagination"]["total_items"] == 3


def test_deberia_aceptar_limit_igual_al_maximo(client, auth_headers):
    assert client.get(URL, params={"limit": 100}, headers=auth_headers).status_code == 200


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0}, {"page": -1}, {"page": "abc"}, {"page": "1.5"}, {"page": ""},
        {"limit": 0}, {"limit": -5}, {"limit": "abc"}, {"limit": 101},
    ],
)
def test_deberia_devolver_400_con_page_o_limit_invalidos(client, auth_headers, params):
    response = client.get(URL, params=params, headers=auth_headers)

    assert response.status_code == 400
    assert response.json()["error"] == "INVALID_QUERY_PARAMS"


def test_deberia_devolver_401_sin_token(client):
    response = client.get(URL)

    assert response.status_code == 401
    assert response.json()["error"] == "UNAUTHORIZED"


def test_deberia_devolver_401_con_token_invalido(client):
    response = client.get(URL, headers={"Authorization": "Bearer token-invalido"})

    assert response.status_code == 401


def test_deberia_devolver_401_con_token_vencido(client, usuario_con_equipo):
    token = create_access_token(
        user_id=usuario_con_equipo.user_id, expires_delta=timedelta(seconds=-1)
    )

    assert client.get(URL, headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_deberia_devolver_401_con_token_de_usuario_inexistente(client):
    token = create_access_token(user_id=9999)

    assert client.get(URL, headers={"Authorization": f"Bearer {token}"}).status_code == 401
