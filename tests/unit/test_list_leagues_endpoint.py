"""
Tests HTTP para GET /api/v1/leagues

Pasan por HTTP de verdad (TestClient): ruta + service + repository + base juntos.
Como todavia no existe POST /leagues, las ligas y los equipos inscriptos se
insertan directo en la base de test.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.core.security import create_access_token
from src.database.base import get_db
from src.main import app
from src.models import Behavior, League, LeagueStatus, LineupEntry, Player, Team
from src.services.league_service import list_leagues

URL = "/api/v1/leagues"


#  Fixtures

@pytest.fixture()
def client(session):
    # Hace que la app use la base de test en vez de la real
    app.dependency_overrides[get_db] = lambda: session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(usuario_con_equipo):
    token = create_access_token(user_id=usuario_con_equipo.user_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def comportamiento(session):
    # lineup_entries.behavior_id es FK obligatoria, asi que hace falta uno real
    behavior = Behavior(
        name="Patear", description="Patea la pelota",
        code="def on_tick(api): pass", is_default=True,
    )
    session.add(behavior)
    session.commit()
    return behavior


# Helpers 

def _crear_liga(session, host_team, nombre="Liga", status=LeagueStatus.PENDING,
                password_hash=None):
    """Inserta una liga. password_hash=None -> publica; con valor -> privada."""
    liga = League(
        league_name=nombre,
        max_teams=8,
        status=status,
        password_hash=password_hash,
        match_duration=5,
        host_team_id=host_team.team_id,
    )
    session.add(liga)
    session.commit()
    return liga


def _crear_equipo(session, nombre):
    equipo = Team(team_name=nombre)
    session.add(equipo)
    session.commit()
    return equipo


def _inscribir(session, liga, equipo, comportamiento, primer_numero=1):
    """
    Inscribe un equipo en la liga como lo hara el POST de unirse:
    6 filas en lineup_entries (3 titulares con rol y 3 suplentes sin rol),
    con league_id y sin match_id.
    """
    roles = ["DEF_LEFT", "DEF_RIGHT", "FORWARD", None, None, None]
    for numero, role in enumerate(roles, start=primer_numero):
        jugador = Player(
            team_id=equipo.team_id, name=f"J{numero}", number=numero,
            power=60, agility=60, control=60, speed=60, strength=60,
        )
        session.add(jugador)
        session.flush()  # para que el jugador tenga player_id antes de la entry
        session.add(LineupEntry(
            league_id=liga.league_id,
            team_id=equipo.team_id,
            player_id=jugador.player_id,
            behavior_id=comportamiento.behavior_id,
            role=role,
            is_starter=role is not None,
        ))
    session.commit()

# --------------------------------------------------------------------------

def test_deberia_devolver_los_campos_de_cada_liga_sin_exponer_la_password(
    client, session, usuario_con_equipo, auth_headers
):
    _crear_liga(session, usuario_con_equipo.team, nombre="Publica")
    _crear_liga(session, usuario_con_equipo.team, nombre="Privada", password_hash="hash-secreto-123")

    response = client.get(URL, headers=auth_headers)

    assert response.status_code == 200
    ligas = {liga["league_name"]: liga for liga in response.json()["leagues"]}
    # Exactamente estos campos: no hay password ni password_hash
    for liga in ligas.values():
        assert set(liga) == {
            "league_id", "league_name", "max_teams", "current_teams_count", "status", "is_private", "is_member",
        }
    assert ligas["Publica"]["is_private"] is False
    assert ligas["Privada"]["is_private"] is True
    assert "hash-secreto-123" not in response.text


def test_deberia_contar_equipos_inscriptos_de_cada_liga(
    client, session, usuario_con_equipo, comportamiento, auth_headers
):
    liga_a = _crear_liga(session, usuario_con_equipo.team, nombre="A")
    liga_b = _crear_liga(session, usuario_con_equipo.team, nombre="B")
    _crear_liga(session, usuario_con_equipo.team, nombre="C")
    # Cada equipo ocupa 6 filas: si se contaran filas, A daria 12 y no 2
    _inscribir(session, liga_a, usuario_con_equipo.team, comportamiento)
    _inscribir(session, liga_a, _crear_equipo(session, "Rival FC"), comportamiento)
    _inscribir(session, liga_b, _crear_equipo(session, "Otro FC"), comportamiento)

    ligas = client.get(URL, headers=auth_headers).json()["leagues"]

    assert {liga["league_name"]: liga["current_teams_count"] for liga in ligas} == {"A": 2, "B": 1, "C": 0}


def test_deberia_filtrar_por_status_y_devolver_todas_si_no_se_envia(
    client, session, usuario_con_equipo, auth_headers
):
    _crear_liga(session, usuario_con_equipo.team, nombre="P", status=LeagueStatus.PENDING)
    _crear_liga(session, usuario_con_equipo.team, nombre="I", status=LeagueStatus.IN_PROGRESS)
    _crear_liga(session, usuario_con_equipo.team, nombre="F", status=LeagueStatus.FINISHED)

    todas = client.get(URL, headers=auth_headers).json()["leagues"]
    assert {liga["league_name"] for liga in todas} == {"P", "I", "F"}

    for status in ["PENDING", "IN_PROGRESS", "FINISHED"]:
        ligas = client.get(URL, params={"status": status}, headers=auth_headers).json()["leagues"]
        assert [liga["status"] for liga in ligas] == [status]


def test_deberia_paginar_segun_page_y_limit_de_la_mas_nueva_a_la_mas_vieja(
    client, session, usuario_con_equipo, auth_headers
):
    for n in range(1, 6):
        _crear_liga(session, usuario_con_equipo.team, nombre=f"L{n}")

    def nombres(page):
        resp = client.get(URL, params={"page": page, "limit": 2}, headers=auth_headers)
        assert resp.status_code == 200
        return [liga["league_name"] for liga in resp.json()["leagues"]]

    assert nombres(1) == ["L5", "L4"]
    assert nombres(2) == ["L3", "L2"]
    assert nombres(3) == ["L1"]


def test_deberia_devolver_200_con_lista_vacia_sin_ligas_o_con_pagina_fuera_de_rango(
    client, session, usuario_con_equipo, auth_headers
):
    sin_ligas = client.get(URL, headers=auth_headers)
    assert sin_ligas.status_code == 200
    assert sin_ligas.json() == {"leagues": []}

    _crear_liga(session, usuario_con_equipo.team)

    fuera_de_rango = client.get(URL, params={"page": 5}, headers=auth_headers)
    assert fuera_de_rango.status_code == 200
    assert fuera_de_rango.json() == {"leagues": []}


def test_deberia_marcar_is_member_en_las_liga_que_participa(
    session, usuario_con_equipo, comportamiento
):
    mi_equipo = usuario_con_equipo.team
    rival = _crear_equipo(session, "Instituto")

    # Anfitrion: creo mi liga y estoy inscripto en ella
    de_anfitrion = _crear_liga(session, mi_equipo, nombre="Anfitrion")
    _inscribir(session, de_anfitrion, mi_equipo, comportamiento)

    # Miembro: crea un rival la liga y me inscribo
    # (primer_numero=7: mi equipo ya uso las camisetas 1 a 6 en la liga anterior)
    de_miembro = _crear_liga(session, rival, nombre="Miembro")
    _inscribir(session, de_miembro, rival, comportamiento)
    _inscribir(session, de_miembro, mi_equipo, comportamiento, primer_numero=7)
    
    # Ajeno: un rival crea una liga y no me inscribo
    de_ajeno = _crear_liga(session, rival, nombre="Ajeno")
    _inscribir(session, de_ajeno, rival, comportamiento, primer_numero=7)

    ligas = list_leagues(session, usuario_con_equipo.user_id, None, None, None)

    assert {liga.league_name: liga.is_member for liga in ligas} == {
        "Anfitrion": True, "Miembro": True, "Ajeno": False,
    }


@pytest.mark.parametrize(
    "params",
    [{"page": 0}, {"page": "abc"}, {"limit": 0}, {"limit": 101}, {"status": "XXX"}],
)
def test_deberia_devolver_400_con_parametros_invalidos(client, auth_headers, params):
    response = client.get(URL, params=params, headers=auth_headers)

    assert response.status_code == 400
    assert response.json()["error"] == "INVALID_QUERY_PARAMS"
