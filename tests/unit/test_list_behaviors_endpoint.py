"""
Tests HTTP para GET /api/v1/behaviors
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from src.core.security import create_access_token
from src.database.base import get_db
from src.main import app
from src.models import Behavior, Team, User

URL = "/api/v1/behaviors"


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
    user = User(
        username="otro", email="otro@example.com", password_hash="x",
        team=Team(team_name="Otro FC"),
    )
    session.add(user)
    session.commit()
    return user


@pytest.fixture()
def comportamientos(session, usuario_con_equipo, otro_usuario):
    """
    2 predeterminados del sistema, 1 personalizado del usuario logueado
    y 1 personalizado de otro usuario.
    """
    default_1 = Behavior(name="Patear al arco", description="d1", code="def on_tick(api): pass", is_default=True)
    default_2 = Behavior(name="Defensor", description="d2", code="def on_tick(api): pass", is_default=True)
    propio = Behavior(
        name="Mi comportamiento", description="p", code="def on_tick(api): pass",
        user_id=usuario_con_equipo.user_id, is_default=False,
    )
    ajeno = Behavior(
        name="De otro", description="a", code="def on_tick(api): pass",
        user_id=otro_usuario.user_id, is_default=False,
    )
    session.add_all([default_1, default_2, propio, ajeno])
    session.commit()
    return {"defaults": [default_1, default_2], "propio": propio, "ajeno": ajeno}


def _nombres(response) -> list[str]:
    return [behavior["name"] for behavior in response.json()]


# 200 

def test_deberia_devolver_200_con_los_predeterminados_y_los_propios(client, auth_headers, comportamientos):
    response = client.get(URL, headers=auth_headers)

    assert response.status_code == 200
    assert _nombres(response) == ["Patear al arco", "Defensor", "Mi comportamiento"]


def test_no_deberia_devolver_comportamientos_personalizados_de_otros_usuarios(client, auth_headers, comportamientos):
    response = client.get(URL, headers=auth_headers)

    assert "De otro" not in _nombres(response)


def test_deberia_devolver_cada_comportamiento_con_los_campos_del_contrato(client, auth_headers, comportamientos):
    response = client.get(URL, headers=auth_headers)

    primero = response.json()[0]
    assert set(primero.keys()) == {"behavior_id", "name", "description", "code", "is_default"}
    assert primero["is_default"] is True


def test_deberia_devolver_una_lista_vacia_si_no_hay_comportamientos(client, auth_headers):
    response = client.get(URL, headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == []


# Filtro is_default 

def test_deberia_devolver_solo_los_predeterminados_con_is_default_true(client, auth_headers, comportamientos):
    response = client.get(URL, params={"is_default": "true"}, headers=auth_headers)

    assert response.status_code == 200
    assert _nombres(response) == ["Patear al arco", "Defensor"]


def test_deberia_devolver_solo_los_propios_con_is_default_false(client, auth_headers, comportamientos):
    response = client.get(URL, params={"is_default": "false"}, headers=auth_headers)

    assert response.status_code == 200
    assert _nombres(response) == ["Mi comportamiento"]


def test_deberia_aceptar_is_default_sin_importar_mayusculas(client, auth_headers, comportamientos):
    response = client.get(URL, params={"is_default": "TRUE"}, headers=auth_headers)

    assert response.status_code == 200
    assert _nombres(response) == ["Patear al arco", "Defensor"]


# 400 INVALID_QUERY_PARAMS 

@pytest.mark.parametrize("valor", ["abc", "1", "si", ""])
def test_deberia_devolver_400_si_is_default_no_es_un_booleano(client, auth_headers, valor):
    response = client.get(URL, params={"is_default": valor}, headers=auth_headers)

    assert response.status_code == 400
    assert response.json()["error"] == "INVALID_QUERY_PARAMS"


# 401 

def test_deberia_devolver_401_sin_token(client):
    response = client.get(URL)

    assert response.status_code == 401
    assert response.json()["error"] == "UNAUTHORIZED"


def test_deberia_devolver_401_con_token_invalido(client):
    response = client.get(URL, headers={"Authorization": "Bearer token-invalido"})

    assert response.status_code == 401
    assert response.json()["error"] == "UNAUTHORIZED"


def test_deberia_devolver_401_con_token_vencido(client, usuario_con_equipo):
    token = create_access_token(
        user_id=usuario_con_equipo.user_id, expires_delta=timedelta(seconds=-1)
    )

    response = client.get(URL, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["error"] == "UNAUTHORIZED"


def test_deberia_devolver_401_con_token_de_usuario_inexistente(client):
    token = create_access_token(user_id=9999)

    response = client.get(URL, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_deberia_devolver_401_antes_que_400_si_falta_el_token(client):
    response = client.get(URL, params={"is_default": "abc"})

    assert response.status_code == 401