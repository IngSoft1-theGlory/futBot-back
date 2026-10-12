"""
Tests HTTP para GET /api/v1/behaviors/{behavior_id}
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


#200

def test_deberia_devolver_200_con_un_comportamiento_predeterminado_patear(client, auth_headers, comportamientos):
    default = comportamientos["defaults"][0]

    response = client.get(f"{URL}/{default.behavior_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["name"] == "Patear al arco"


def test_deberia_devolver_200_con_un_comportamiento_predeterminado_defender(client, auth_headers, comportamientos):
    default = comportamientos["defaults"][1]

    response = client.get(f"{URL}/{default.behavior_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["name"] == "Defensor"


def test_deberia_devolver_los_campos_del_comportamiento(client, auth_headers, comportamientos):
    default = comportamientos["defaults"][0]

    response = client.get(f"{URL}/{default.behavior_id}", headers=auth_headers)

    comportamiento = response.json()
    assert set(comportamiento.keys()) == {"behavior_id", "name", "description", "code", "is_default"}
    assert comportamiento["is_default"] is True


def test_deberia_devolver_200_con_un_comportamiento_propio(client, auth_headers, comportamientos):
    owner = comportamientos["propio"]

    response = client.get(f"{URL}/{owner.behavior_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["name"] == "Mi comportamiento"


# 404

def test_deberia_devolver_404_si_el_comportamiento_no_existe(client, auth_headers):
    response = client.get(f"{URL}/9999", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["error"] == "BEHAVIOR_NOT_FOUND"


def test_no_deberia_devolver_comportamientos_de_otros_usuarios(client, auth_headers, comportamientos):
    another = comportamientos["ajeno"]
    
    response = client.get(f"{URL}/{another.behavior_id}", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["error"] == "BEHAVIOR_NOT_FOUND"    

