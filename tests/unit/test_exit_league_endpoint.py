"""
Tests del endpoint DELETE /api/v1/leagues/{league_id}/teams/{team_id} (abandonar una liga).

Pasan por HTTP de verdad (TestClient). Un test por criterio de aceptación del ticket.
"""

import pytest
from sqlalchemy import func, select

from src.models import League, LeagueStatus, LineupEntry, Team, User

# Reutiliza fixtures (db, client, usuario, comportamiento) y helpers del test de crear amistoso
from tests.unit.test_post_friendly_endpoint import (  # noqa: F401
    client, comportamiento, crear_jugadores, db, headers, usuario,
)


def url(league_id, team_id):
    return f"/api/v1/leagues/{league_id}/teams/{team_id}"


def inscribir(db, liga, equipo, comportamiento):
    """Inscribe al equipo en la liga: guarda sus 6 filas de lineup_entries con league_id."""
    jugadores = crear_jugadores(db, equipo)
    roles = ["DEF_LEFT", "DEF_RIGHT", "FORWARD", None, None, None]
    db.add_all(
        LineupEntry(
            league_id=liga.league_id, team_id=equipo.team_id, player_id=j.player_id,
            behavior_id=comportamiento.behavior_id, role=rol, is_starter=rol is not None,
        )
        for j, rol in zip(jugadores, roles)
    )
    db.commit()


def filas(db, liga, team_id):
    """Cantidad de filas de inscripción que tiene el equipo en la liga."""
    return db.scalar(
        select(func.count()).select_from(LineupEntry)
        .where(LineupEntry.league_id == liga.league_id, LineupEntry.team_id == team_id)
    )


@pytest.fixture()
def liga(db, usuario, comportamiento):
    """Liga PENDING cuyo anfitrión es `usuario`, con su alineación ya inscripta."""
    liga = League(league_name="Copa", max_teams=8, match_duration=5, host_team_id=usuario.team_id)
    db.add(liga)
    db.commit()
    inscribir(db, liga, usuario.team, comportamiento)
    return liga


@pytest.fixture()
def invitado(db):
    """Usuario con equipo que todavía NO está inscripto en la liga."""
    user = User(
        username="cr7", email="cr7@example.com",
        password_hash="hash-falso", team=Team(team_name="Rival FC"),
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture()
def inscripto(db, liga, invitado, comportamiento):
    """El mismo `invitado`, ya inscripto en la liga."""
    inscribir(db, liga, invitado.team, comportamiento)
    return invitado


def test_deberia_devolver_204_y_borrar_la_inscripcion_del_equipo(client, db, liga, inscripto):
    r = client.delete(url(liga.league_id, inscripto.team_id), headers=headers(inscripto))

    assert r.status_code == 204
    assert r.content == b""
    assert filas(db, liga, inscripto.team_id) == 0
    assert filas(db, liga, liga.host_team_id) == 6  # el anfitrión no se toca


def test_deberia_devolver_400_host_cannot_leave_si_sale_el_anfitrion(client, db, usuario, liga):
    r = client.delete(url(liga.league_id, usuario.team_id), headers=headers(usuario))

    assert r.status_code == 400
    assert r.json()["error"] == "HOST_CANNOT_LEAVE"
    assert filas(db, liga, usuario.team_id) == 6


def test_deberia_devolver_403_si_el_team_id_es_de_otro_usuario(client, db, usuario, liga, inscripto):
    # el anfitrión intenta sacar al equipo de otro: tampoco puede
    r = client.delete(url(liga.league_id, inscripto.team_id), headers=headers(usuario))

    assert r.status_code == 403
    assert filas(db, liga, inscripto.team_id) == 6


def test_deberia_devolver_404_team_not_in_league_si_el_equipo_no_esta_inscripto(client, liga, invitado):
    r = client.delete(url(liga.league_id, invitado.team_id), headers=headers(invitado))

    assert r.status_code == 404
    assert r.json()["error"] == "TEAM_NOT_IN_LEAGUE"


def test_deberia_devolver_404_league_not_found_si_la_liga_no_existe(client, usuario):
    r = client.delete(url(9999, usuario.team_id), headers=headers(usuario))

    assert r.status_code == 404
    assert r.json()["error"] == "LEAGUE_NOT_FOUND"


def test_deberia_devolver_409_league_already_started_si_la_liga_no_esta_pending(client, db, liga, inscripto):
    liga.status = LeagueStatus.IN_PROGRESS
    db.commit()

    r = client.delete(url(liga.league_id, inscripto.team_id), headers=headers(inscripto))

    assert r.status_code == 409
    assert r.json()["error"] == "LEAGUE_ALREADY_STARTED"
    assert filas(db, liga, inscripto.team_id) == 6


def test_deberia_devolver_401_sin_token(client, liga, inscripto):
    r = client.delete(url(liga.league_id, inscripto.team_id))

    assert r.status_code == 401