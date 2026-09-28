"""
Tests HTTP para POST /api/v1/auth/login.

Ticket (GLORY-102):
  Dado un usuario con cuenta ya creada, al enviar email + contraseña
  correctos el sistema responde 200 OK con un objeto `user` (user_id,
  team_id, email, username) y un token de sesión. Si el email o la
  contraseña son incorrectos, responde 401 UNAUTHORIZED.

Igual que en test_register_endpoint.py, estos son tests "de afuera hacia
adentro": pegan contra la ruta HTTP real con el TestClient de FastAPI, no
llaman a las funciones de servicio directamente. Así confirmamos lo que
un cliente (el frontend) realmente ve: status code, shape del JSON y
error codes exactos del contrato.

Para tener un usuario con una contraseña conocida (necesitamos la
contraseña en texto plano para poder loguearnos con ella, cosa que la
fixture `usuario_con_equipo` de conftest.py no nos da: guarda un
password_hash falso, no un hash bcrypt real), cada test registra su
propio usuario primero pegándole a POST /api/v1/auth/register.
"""

from __future__ import annotations

import jwt
import pytest
from fastapi.testclient import TestClient

from src.config.settings import settings
from src.core.security import ALGORITHM
from src.database.base import get_db
from src.main import app

REGISTER_PAYLOAD = {
    "username": "Maradona10",
    "email": "diego@famaf.unc.edu.ar",
    "password": "Password123!",
    "team_name": "alfajoresFC",
    "team_logo": "https://example.com/logos/alfajores.png",
}

LOGIN_PAYLOAD = {
    "email": REGISTER_PAYLOAD["email"],
    "password": REGISTER_PAYLOAD["password"],
}


@pytest.fixture()
def client(session):
    app.dependency_overrides[get_db] = lambda: session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def usuario_registrado(client):
    """Registra un usuario real (via HTTP, no accediendo a la DB
    directamente) y devuelve el body de la respuesta de registro, para
    poder comparar user_id/team_id contra lo que devuelva el login."""
    response = client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------
# Camino feliz
# ---------------------------------------------------------------------


def test_login_returns_200_with_expected_shape(client, usuario_registrado):
    response = client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"token", "token_type", "user"}
    assert set(body["user"].keys()) == {"user_id", "team_id", "username", "email"}


def test_login_token_type_is_bearer(client, usuario_registrado):
    response = client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)

    assert response.json()["token_type"] == "Bearer"


def test_login_user_object_matches_registered_user(client, usuario_registrado):
    response = client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)

    user = response.json()["user"]
    assert user["user_id"] == usuario_registrado["user_id"]
    assert user["team_id"] == usuario_registrado["team_id"]
    assert user["username"] == REGISTER_PAYLOAD["username"]
    assert user["email"] == REGISTER_PAYLOAD["email"]


def test_login_token_is_valid_jwt_for_the_logged_in_user(client, usuario_registrado):
    """No alcanza con chequear que 'token' sea un string no vacío: hay
    que decodificarlo y confirmar que el 'sub' es el user_id correcto.
    Sin este test, un endpoint que devuelva cualquier string fijo como
    token pasaría igual las validaciones de shape."""
    response = client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
    token = response.json()["token"]

    payload = jwt.decode(token, key=settings.SECRET_KEY, algorithms=[ALGORITHM])

    assert int(payload["sub"]) == usuario_registrado["user_id"]
    assert "exp" in payload


def test_login_password_not_in_response(client, usuario_registrado):
    response = client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)

    assert "password_hash" not in response.text
    assert REGISTER_PAYLOAD["password"] not in response.text


# ---------------------------------------------------------------------
# 401 — credenciales incorrectas
# ---------------------------------------------------------------------


def test_login_wrong_password_returns_401(client, usuario_registrado):
    response = client.post(
        "/api/v1/auth/login",
        json={**LOGIN_PAYLOAD, "password": "OtraPassword456!"},
    )

    assert response.status_code == 401
    assert response.json()["error"] == "INVALID_CREDENTIALS"


def test_login_nonexistent_email_returns_401(client):
    """Ni siquiera hace falta que exista un usuario registrado: pedir
    login con un email que no está en la base también es 401
    INVALID_CREDENTIALS (no 404): así lo pide el contrato."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "nadie@famaf.unc.edu.ar", "password": "Cualquiera123!"},
    )

    assert response.status_code == 401
    assert response.json()["error"] == "INVALID_CREDENTIALS"


def test_login_wrong_password_and_nonexistent_email_return_identical_error_body(
    client, usuario_registrado
):
    """Chequeo de seguridad, no solo de contrato: la respuesta para
    'existe el email pero la password está mal' y para 'el email ni
    existe' tienen que ser byte a byte la misma. Si no lo fueran,
    alguien podría usar el endpoint de login para enumerar qué emails
    están registrados probando contraseñas al azar."""
    wrong_password = client.post(
        "/api/v1/auth/login",
        json={**LOGIN_PAYLOAD, "password": "OtraPassword456!"},
    )
    nonexistent_email = client.post(
        "/api/v1/auth/login",
        json={"email": "nadie@famaf.unc.edu.ar", "password": "OtraPassword456!"},
    )

    assert wrong_password.status_code == nonexistent_email.status_code == 401
    assert wrong_password.json() == nonexistent_email.json()


def test_login_empty_password_returns_401_not_500(client, usuario_registrado):
    """Caso límite: password vacío es un string válido para el schema
    (Pydantic no lo rechaza), así que tiene que llegar hasta
    verify_password() y fallar ahí con 401, en vez de romper el server
    con un 500 (bcrypt.checkpw podría no tolerar bien un string vacío
    si no se lo maneja)."""
    response = client.post(
        "/api/v1/auth/login", json={**LOGIN_PAYLOAD, "password": ""}
    )

    assert response.status_code == 401
    assert response.json()["error"] == "INVALID_CREDENTIALS"


@pytest.mark.xfail(
    reason=(
        "BUG sospechado: create_user_with_team guarda el email en minúsculas, "
        "pero get_user_by_email() en el login no normaliza el email recibido "
        "antes de buscarlo. Un usuario que se registró con mayúsculas en el "
        "email no puede loguearse escribiéndolo tal cual lo registró."
    ),
    strict=False,
)
def test_login_email_is_case_insensitive(client):
    mixed_case_payload = {
        **REGISTER_PAYLOAD,
        "email": "Diego@FAMAF.unc.edu.ar",
    }
    register_response = client.post("/api/v1/auth/register", json=mixed_case_payload)
    assert register_response.status_code == 201, register_response.text

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": mixed_case_payload["email"], "password": mixed_case_payload["password"]},
    )

    assert login_response.status_code == 200


# ---------------------------------------------------------------------
# 422 — errores de forma del body (frontera Pydantic, no del contrato de negocio)
# ---------------------------------------------------------------------


def test_login_missing_email_field_returns_422(client):
    response = client.post("/api/v1/auth/login", json={"password": "Password123!"})

    assert response.status_code == 422


def test_login_missing_password_field_returns_422(client):
    response = client.post(
        "/api/v1/auth/login", json={"email": REGISTER_PAYLOAD["email"]}
    )

    assert response.status_code == 422


def test_login_malformed_email_returns_422(client):
    """LoginRequest usa EmailStr (a diferencia de RegisterRequest, que
    usa un str simple y valida el formato a mano con un 400
    INVALID_FORMAT). Por eso acá un email mal formado corta antes,
    con 422 de Pydantic, y nunca llega a devolver el 401 genérico."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "no-es-un-email", "password": "Password123!"},
    )

    assert response.status_code == 422