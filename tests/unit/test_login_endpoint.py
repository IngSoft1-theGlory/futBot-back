"""
Tests HTTP para POST /api/v1/auth/login
"""

from __future__ import annotations

import jwt
import pytest
from fastapi.testclient import TestClient

from src.config.settings import settings
from src.core.security import ALGORITHM
from src.database.base import get_db
from src.main import app

# Body válido para registrar el usuario que después usamos para loguearnos.
REGISTER_PAYLOAD = {
    "username": "Maradona10",
    "email": "diego@famaf.unc.edu.ar",
    "password": "Password123!",
    "team_name": "alfajoresFC",
    "team_logo": "https://example.com/logos/alfajores.png",
}

# Mismo email/password que REGISTER_PAYLOAD, pero solo los dos campos
# que espera el body de /auth/login.
LOGIN_PAYLOAD = {
    "email": REGISTER_PAYLOAD["email"],
    "password": REGISTER_PAYLOAD["password"],
}


@pytest.fixture()
def client(session):
    # Reemplaza get_db (que normalmente abriría una conexión real) por la
    # fixture `session` de conftest.py (SQLite en memoria).
    app.dependency_overrides[get_db] = lambda: session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def usuario_registrado(client):
    """Registra un usuario real (via HTTP) y devuelve el body de la
    respuesta de registro, para comparar user_id/team_id contra lo que
    devuelva el login."""
    response = client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    assert response.status_code == 201, response.text
    return response.json()


def test_login_devuelve_200_y_los_datos_correctos_con_credenciales_validas(
    client, usuario_registrado
):
    """Chequea status, shape exacto del body, token_type fijo, los datos del usuario devueltos, y
    que el token sea un JWT real (no cualquier string) firmado para ese
    user_id"""
    response = client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"token", "token_type", "user"}
    assert body["token_type"] == "Bearer"

    user = body["user"]
    assert user["user_id"] == usuario_registrado["user_id"]
    assert user["team_id"] == usuario_registrado["team_id"]
    assert user["username"] == REGISTER_PAYLOAD["username"]
    assert user["email"] == REGISTER_PAYLOAD["email"]

    # Decodifica el JWT con la misma SECRET_KEY del server: si la
    # firma no coincidiera, jwt.decode() tiraria una excepción
    payload = jwt.decode(body["token"], key=settings.SECRET_KEY, algorithms=[ALGORITHM])
    assert int(payload["sub"]) == usuario_registrado["user_id"]


def test_login_password_no_aparece_en_la_respuesta(client, usuario_registrado):
    # Ni el hash ni la contraseña en texto plano pueden
    # aparecer en ningún lado del JSON de respuesta.
    response = client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)

    assert "password_hash" not in response.text
    assert REGISTER_PAYLOAD["password"] not in response.text


def test_login_password_incorrecta_devuelve_401(client, usuario_registrado):
    # Mismo email que el usuario registrado, pero password distinta.
    response = client.post(
        "/api/v1/auth/login",
        json={**LOGIN_PAYLOAD, "password": "OtraPassword456!"},
    )

    assert response.status_code == 401
    assert response.json()["error"] == "INVALID_CREDENTIALS"


def test_login_email_inexistente_devuelve_401(client):
    # un email que no está en la base debe dar 401 INVALID_CREDENTIALS (no 404).
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "nadie@famaf.unc.edu.ar", "password": "Cualquiera123!"},
    )

    assert response.status_code == 401
    assert response.json()["error"] == "INVALID_CREDENTIALS"


def test_login_password_vacia_devuelve_401_no_500(client, usuario_registrado):
    """ un input raro nunca tiene que tirar un 500: password vacío es un string válido para el schema (Pydantic
    no lo rechaza), así que tiene que llegar hasta verify_password() y
    fallar ahí con 401 controlado, no con una excepción sin manejar
    (bcrypt.checkpw podría no tolerar bien un string vacío)."""
    response = client.post(
        "/api/v1/auth/login", json={**LOGIN_PAYLOAD, "password": ""}
    )

    assert response.status_code == 401
    assert response.json()["error"] == "INVALID_CREDENTIALS"
