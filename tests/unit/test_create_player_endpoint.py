"""
Tests HTTP para POST /api/v1/players
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

# Suma 300, todos dentro de 20-100
VALID_PAYLOAD = {
    "name": "Lionel",
    "number": 10,
    "power": 60,
    "agility": 60,
    "control": 60,
    "speed": 60,
    "strength": 60,
}


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


def _payload(**overrides):
    return {**VALID_PAYLOAD, **overrides}


def _players_count(session) -> int:
    return session.query(Player).count()


def test_deberia_devolver_201_y_persistir_el_jugador_en_el_equipo_del_usuario(
    client, session, usuario_con_equipo, auth_headers
):
    response = client.post(URL, json=VALID_PAYLOAD, headers=auth_headers)

    assert response.status_code == 201
    body = response.json()
    assert set(body.keys()) == {
        "player_id", "name", "number", "power", "agility", "control", "speed", "strength",
    }
    assert {k: body[k] for k in VALID_PAYLOAD} == VALID_PAYLOAD

    player = session.get(Player, body["player_id"])
    assert player.team_id == usuario_con_equipo.team_id


def test_deberia_ignorar_el_team_id_del_body(client, session, usuario_con_equipo, auth_headers):
    otro_equipo = Team(team_name="Otro FC")
    session.add(otro_equipo)
    session.commit()

    response = client.post(
        URL, json=_payload(team_id=otro_equipo.team_id), headers=auth_headers
    )

    assert response.status_code == 201
    player = session.get(Player, response.json()["player_id"])
    assert player.team_id == usuario_con_equipo.team_id


def test_deberia_guardar_el_nombre_sin_espacios_sobrantes(client, auth_headers):
    response = client.post(URL, json=_payload(name="  Lionel  "), headers=auth_headers)

    assert response.status_code == 201
    assert response.json()["name"] == "Lionel"


def test_deberia_permitir_el_mismo_numero_en_dos_equipos_distintos(client, session, auth_headers):
    assert client.post(URL, json=VALID_PAYLOAD, headers=auth_headers).status_code == 201

    otro_usuario = User(
        username="otro", email="otro@example.com", password_hash="x",
        team=Team(team_name="Otro FC"),
    )
    session.add(otro_usuario)
    session.commit()
    otro_token = create_access_token(user_id=otro_usuario.user_id)

    response = client.post(
        URL, json=VALID_PAYLOAD, headers={"Authorization": f"Bearer {otro_token}"}
    )

    assert response.status_code == 201


# ---------- 401 ----------

def test_deberia_devolver_401_sin_token(client, session):
    response = client.post(URL, json=VALID_PAYLOAD)

    assert response.status_code == 401
    assert response.json()["error"] == "UNAUTHORIZED"
    assert _players_count(session) == 0


def test_deberia_devolver_401_con_token_invalido(client):
    response = client.post(
        URL, json=VALID_PAYLOAD, headers={"Authorization": "Bearer token-invalido"}
    )

    assert response.status_code == 401
    assert response.json()["error"] == "UNAUTHORIZED"


def test_deberia_devolver_401_con_token_vencido(client, usuario_con_equipo):
    token = create_access_token(
        user_id=usuario_con_equipo.user_id, expires_delta=timedelta(seconds=-1)
    )

    response = client.post(
        URL, json=VALID_PAYLOAD, headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401
    assert response.json()["error"] == "UNAUTHORIZED"


def test_deberia_devolver_401_con_token_de_usuario_inexistente(client):
    token = create_access_token(user_id=9999)

    response = client.post(
        URL, json=VALID_PAYLOAD, headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401


def test_deberia_devolver_401_antes_que_422_si_falta_el_token(client):
    # body inválido + sin token: el token se valida antes de leer el body
    response = client.post(URL, json={})

    assert response.status_code == 401


# ---------- 400 INVALID_PACSS_TOTAL ----------

@pytest.mark.parametrize(
    "attributes",
    [
        # un atributo en 19 (suma 300) / 101 (suma 300)
        {"power": 19, "agility": 61, "control": 60, "speed": 60, "strength": 60},
        {"power": 101, "agility": 20, "control": 60, "speed": 59, "strength": 60},
        # bordes válidos por fuera del rango: 0 y negativo
        {"power": 0, "agility": 80, "control": 80, "speed": 70, "strength": 70},
        {"power": -1, "agility": 81, "control": 80, "speed": 70, "strength": 70},
    ],
)
def test_deberia_devolver_400_si_un_atributo_esta_fuera_de_rango(client, session, auth_headers, attributes):
    response = client.post(URL, json=_payload(**attributes), headers=auth_headers)

    assert response.status_code == 400
    assert response.json()["error"] == "INVALID_PACSS_TOTAL"
    assert _players_count(session) == 0


@pytest.mark.parametrize(
    "attributes",
    [
        {"power": 59},   # suma 299
        {"power": 61},   # suma 301
    ],
)
def test_deberia_devolver_400_si_la_suma_es_distinta_de_300(client, session, auth_headers, attributes):
    response = client.post(URL, json=_payload(**attributes), headers=auth_headers)

    assert response.status_code == 400
    assert response.json()["error"] == "INVALID_PACSS_TOTAL"
    assert _players_count(session) == 0


@pytest.mark.parametrize(
    "attributes",
    [
        # 20 y 100 son valores permitidos (ambos casos suman 300)
        {"power": 100, "agility": 80, "control": 20, "speed": 20, "strength": 80},
        {"power": 20, "agility": 100, "control": 100, "speed": 40, "strength": 40},
    ],
)
def test_deberia_aceptar_atributos_en_los_bordes_20_y_100(client, auth_headers, attributes):
    response = client.post(URL, json=_payload(**attributes), headers=auth_headers)

    assert response.status_code == 201


# ---------- 400 INVALID_PLAYER_DATA ----------

@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
def test_deberia_devolver_400_si_el_nombre_es_invalido(client, session, auth_headers, name):
    response = client.post(URL, json=_payload(name=name), headers=auth_headers)

    assert response.status_code == 400
    assert response.json()["error"] == "INVALID_PLAYER_DATA"
    assert _players_count(session) == 0


@pytest.mark.parametrize("number", [0, -1, 2**31])
def test_deberia_devolver_400_si_el_numero_es_invalido(client, session, auth_headers, number):
    response = client.post(URL, json=_payload(number=number), headers=auth_headers)

    assert response.status_code == 400
    assert response.json()["error"] == "INVALID_PLAYER_DATA"
    assert _players_count(session) == 0


# ---------- 400 DUPLICATE_JERSEY_NUMBER ----------

def test_deberia_devolver_400_si_el_numero_esta_repetido_en_el_equipo(client, session, auth_headers):
    assert client.post(URL, json=VALID_PAYLOAD, headers=auth_headers).status_code == 201

    response = client.post(URL, json=_payload(name="Otro"), headers=auth_headers)

    assert response.status_code == 400
    assert response.json()["error"] == "DUPLICATE_JERSEY_NUMBER"
    assert _players_count(session) == 1


# ---------- 422 VALIDATION_ERROR ----------

@pytest.mark.parametrize("field", list(VALID_PAYLOAD))
def test_deberia_devolver_422_si_falta_un_campo(client, session, auth_headers, field):
    body = {k: v for k, v in VALID_PAYLOAD.items() if k != field}

    response = client.post(URL, json=body, headers=auth_headers)

    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"
    assert _players_count(session) == 0


@pytest.mark.parametrize("bad_value", [50.5, "50", True])
@pytest.mark.parametrize("field", ["number", "power", "agility", "control", "speed", "strength"])
def test_deberia_devolver_422_si_un_valor_tiene_tipo_incorrecto(client, session, auth_headers, field, bad_value):
    response = client.post(URL, json=_payload(**{field: bad_value}), headers=auth_headers)

    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"
    assert _players_count(session) == 0
