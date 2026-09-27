"""
Tests HTTP para POST /api/v1/auth/register.

test_user_persistence.py ya cubre la lógica de negocio (atomicidad,
hashing, cascada, etc.) llamando directo a create_user_with_team(). Estos
tests son "de afuera hacia adentro": usan el TestClient de FastAPI para
confirmar que la ruta HTTP real devuelve los status codes, el shape de
response y los error codes exactos que pide el contrato — que es lo que
un cliente (el frontend) realmente ve.

Reutilizamos la fixture `session` de tests/conftest.py (SQLite en memoria)
y la inyectamos en la app vía dependency_overrides, para no depender de
DATABASE_URL ni de una base real.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.database.base import get_session
from src.main import app

VALID_PAYLOAD = {
    "username": "Maradona10",
    "email": "diego@famaf.unc.edu.ar",
    "password": "Password123!",
    "team_name": "alfajoresFC",
    "team_logo": "https://example.com/logos/alfajores.png",
}


@pytest.fixture()
def client(session):
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_register_returns_201_with_expected_shape(client):
    response = client.post("/api/v1/auth/register", json=VALID_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert set(body.keys()) == {
        "user_id", "team_id", "username", "email", "team_name", "team_logo",
    }
    assert body["username"] == VALID_PAYLOAD["username"]
    assert body["email"] == VALID_PAYLOAD["email"]
    assert body["team_name"] == VALID_PAYLOAD["team_name"]
    assert body["team_logo"] == VALID_PAYLOAD["team_logo"]
    assert isinstance(body["user_id"], int)
    assert isinstance(body["team_id"], int)


def test_register_password_not_in_response(client):
    response = client.post("/api/v1/auth/register", json=VALID_PAYLOAD)

    assert "password" not in response.text
    assert "password_hash" not in response.text
    assert VALID_PAYLOAD["password"] not in response.text


def test_register_duplicate_email_returns_400(client):
    client.post("/api/v1/auth/register", json=VALID_PAYLOAD)
    
    response = client.post(
        "/api/v1/auth/register",
        json={**VALID_PAYLOAD, "username": "OtroUsuario"},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "DUPLICATE_EMAIL"


def test_register_empty_username_returns_400(client):
    response = client.post(
        "/api/v1/auth/register", json={**VALID_PAYLOAD, "username": "   "}
    )

    assert response.status_code == 400
    assert response.json()["error"] == "VOID_USERNAME"


def test_register_invalid_email_format_returns_400(client):
    response = client.post(
        "/api/v1/auth/register", json={**VALID_PAYLOAD, "email": "no-es-un-email"}
    )

    assert response.status_code == 400
    assert response.json()["error"] == "INVALID_FORMAT"


def test_register_empty_team_name_returns_400(client):
    response = client.post(
        "/api/v1/auth/register", json={**VALID_PAYLOAD, "team_name": "   "}
    )

    assert response.status_code == 400
    assert response.json()["error"] == "VOID_TEAM_NAME"


def test_register_empty_team_logo_returns_400(client):
    response = client.post(
        "/api/v1/auth/register", json={**VALID_PAYLOAD, "team_logo": ""}
    )

    assert response.status_code == 400
    assert response.json()["error"] == "VOID_TEAM_LOGO"


def test_register_invalid_logo_format_returns_400(client):
    response = client.post(
        "/api/v1/auth/register",
        json={**VALID_PAYLOAD, "team_logo": "no-es-url-ni-tiene-extension"},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "INVALID_LOGO_FORMAT"


def test_register_missing_field_returns_422_not_400(client):
    """Si falta un campo del body directamente (no vacío, AUSENTE), es un
    error de *forma* que Pydantic detecta antes de llegar al service:
    FastAPI responde 422, no el 400 del contrato de negocio. Este test
    documenta esa frontera a propósito."""
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "team_logo"}

    response = client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 422
