# tests/unit/test_match_endpoint.py
import pytest
from fastapi.testclient import TestClient

from src.core.security import create_access_token  # ← VERIFICÁ el nombre real (mirá test_jwt.py)
from src.database.base import get_db
from src.main import app
from src.models.match import Match, MatchStatus
from src.models.team import Team

URL = "/api/v1/friendly"


@pytest.fixture()
def client(session):
    # La app usaría la base real (futbot.db). Acá la cambiamos por la
    # sesión de test, para que el endpoint vea los partidos que creamos.
    app.dependency_overrides[get_db] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()  # que no se filtre a otros tests


@pytest.fixture()
def auth_headers(usuario_con_equipo):
    # ← VERIFICÁ qué recibe create_access_token (user_id, dict, User) mirando test_jwt.py
    token = create_access_token(usuario_con_equipo.user_id)
    return {"Authorization": f"Bearer {token}"}


def make_team(session, name):
    team = Team(team_name=name)
    session.add(team)
    session.commit()
    return team


def make_match(session, host, away=None, status=MatchStatus.PENDING, duration=10):
    match = Match(
        team_host_id=host.team_id,
        team_away_id=away.team_id if away else None,
        status=status,
        match_duration=duration,
    )
    session.add(match)
    session.commit()
    return match


def test_debe_devolver_401_cuando_no_se_envia_token(client):
    assert client.get(URL).status_code == 401


def test_debe_devolver_lista_vacia_con_200_cuando_no_existen_partidos(client, auth_headers):
    response = client.get(URL, headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"matches": []}


def test_debe_devolver_team_away_id_null_cuando_el_partido_no_tiene_visitante(
    client, auth_headers, session
):
    host = make_team(session, "host")
    make_match(session, host)

    matches = client.get(URL, headers=auth_headers).json()["matches"]

    assert matches[0]["team_away_id"] is None


def test_debe_devolver_solo_los_campos_del_contrato_en_cada_partido(
    client, auth_headers, session
):
    make_match(session, make_team(session, "host"))

    matches = client.get(URL, headers=auth_headers).json()["matches"]

    assert set(matches[0]) == {
        "match_id", "team_host_id", "team_away_id", "status", "match_duration"
    }


def test_debe_devolver_solo_pending_cuando_no_se_indica_status(
    client, auth_headers, session
):
    host = make_team(session, "host")
    away = make_team(session, "away")
    make_match(session, host)
    make_match(session, host, away, MatchStatus.IN_PROGRESS)
    make_match(session, host, away, MatchStatus.FINISHED)

    matches = client.get(URL, headers=auth_headers).json()["matches"]

    assert [m["status"] for m in matches] == ["PENDING"]


def test_debe_devolver_solo_finished_cuando_status_es_finished(
    client, auth_headers, session
):
    host = make_team(session, "host")
    away = make_team(session, "away")
    make_match(session, host)
    make_match(session, host, away, MatchStatus.FINISHED)

    matches = client.get(f"{URL}?status=FINISHED", headers=auth_headers).json()["matches"]

    assert [m["status"] for m in matches] == ["FINISHED"]


def test_debe_devolver_5_partidos_cuando_page_es_3_limit_10_y_hay_25(
    client, auth_headers, session
):
    host = make_team(session, "host")
    for _ in range(25):
        make_match(session, host)

    matches = client.get(f"{URL}?page=3&limit=10", headers=auth_headers).json()["matches"]

    assert len(matches) == 5  # 25 = 10 + 10 + 5


def test_debe_ordenar_los_partidos_por_match_id_descendente(
    client, auth_headers, session
):
    host = make_team(session, "host")
    for _ in range(5):
        make_match(session, host)

    matches = client.get(URL, headers=auth_headers).json()["matches"]

    ids = [m["match_id"] for m in matches]
    assert ids == sorted(ids, reverse=True)


def test_debe_devolver_lista_vacia_cuando_page_supera_el_total_de_paginas(
    client, auth_headers, session
):
    make_match(session, make_team(session, "host"))

    response = client.get(f"{URL}?page=4", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"matches": []}


def test_debe_devolver_20_partidos_cuando_no_se_indica_limit(
    client, auth_headers, session
):
    host = make_team(session, "host")
    for _ in range(25):
        make_match(session, host)

    matches = client.get(URL, headers=auth_headers).json()["matches"]

    assert len(matches) == 20


@pytest.mark.parametrize(
    "query",
    ["page=0", "limit=0", "limit=101", "status=BASURA", "page=abc"],
    ids=["page_cero", "limit_cero", "limit_sobre_el_tope", "status_inexistente", "page_no_numerico"],
)
def test_debe_devolver_422_cuando_un_parametro_de_consulta_es_invalido(
    client, auth_headers, query
):
    assert client.get(f"{URL}?{query}", headers=auth_headers).status_code == 422