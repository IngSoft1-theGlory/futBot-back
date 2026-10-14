"""
Tests del endpoint DELETE /api/v1/leagues/{league_id}/teams/{team_id} (abandonar una liga).

Pasan por HTTP de verdad (TestClient). Un test por criterio de aceptación del ticket.
"""

import pytest
from sqlalchemy import func, select

from src.models import League, LeagueStatus, LineupEntry, Team, User
from src.realtime.event_bus import event_bus

# Reutiliza fixtures (db, client, usuario, comportamiento) y helpers del test de crear amistoso
from tests.unit.test_post_friendly_endpoint import (  
    client, comportamiento, crear_jugadores, db, headers, usuario
)


def url(league_id, team_id):
    """ se crea la direccion del endpoint para no repetirla en cada test """
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
    # El cliente realiza una peticion DELETE al endpoint para que el equipo abandone la liga
    # se pasa direccion y headers de atentificacion de usuario inscripto, guardando la respuesta en `r`
    r = client.delete(url(liga.league_id, inscripto.team_id), headers=headers(inscripto))

    assert r.status_code == 204
    assert r.content == b""                         # si no hay contenido, el body es vacío
    assert filas(db, liga, inscripto.team_id) == 0  # el equipo ya no tiene filas de inscripción en la liga
    assert filas(db, liga, liga.host_team_id) == 6  # el anfitrión sigue con sus 6 filas de inscripción


def test_deberia_devolver_400_host_cannot_leave_si_sale_el_anfitrion(client, db, usuario, liga):
    r = client.delete(url(liga.league_id, usuario.team_id), headers=headers(usuario))

    assert r.status_code == 400
    assert r.json()["error"] == "HOST_CANNOT_LEAVE" # el anfitrión no puede abandonar su propia liga
    assert filas(db, liga, usuario.team_id) == 6    # el anfitrión sigue con sus 6 filas de inscripción en la liga

def test_deberia_devolver_403_si_el_team_id_es_de_otro_usuario(client, db, usuario, liga, inscripto):
    # el anfitrión intenta sacar al equipo de otro: tampoco puede
    r = client.delete(url(liga.league_id, inscripto.team_id), headers=headers(usuario))

    assert r.status_code == 403
    assert filas(db, liga, inscripto.team_id) == 6  # el equipo sigue con sus 6 filas de inscripción en la liga


def test_deberia_devolver_404_team_not_in_league_si_el_equipo_no_esta_inscripto(client, liga, invitado):
    r = client.delete(url(liga.league_id, invitado.team_id), headers=headers(invitado))

    assert r.status_code == 404
    assert r.json()["error"] == "TEAM_NOT_IN_LEAGUE"    # el equipo no estaba inscripto en la liga


def test_deberia_devolver_404_league_not_found_si_la_liga_no_existe(client, usuario):
    r = client.delete(url(9999, usuario.team_id), headers=headers(usuario))

    assert r.status_code == 404
    assert r.json()["error"] == "LEAGUE_NOT_FOUND"    # la liga con id 9999 no existe


def test_deberia_devolver_409_league_already_started_si_la_liga_no_esta_pending(client, db, liga, inscripto):
    liga.status = LeagueStatus.IN_PROGRESS
    db.commit()

    # El cliente realiza una peticion DELETE al endpoint para que el equipo abandone la liga
    # se pasa direccion y headers de atentificacion de usuario inscripto, guardando la respuesta en `r`
    r = client.delete(url(liga.league_id, inscripto.team_id), headers=headers(inscripto))

    assert r.status_code == 409
    assert r.json()["error"] == "LEAGUE_ALREADY_STARTED"    # la liga ya no esta en PENDING, no se puede abandonar
    assert filas(db, liga, inscripto.team_id) == 6          # el equipo sigue con sus 6 filas de inscripción en la liga


def test_deberia_publicar_league_team_left_si_el_equipo_abandona(client, liga, inscripto):
    queue = event_bus.subscribe()

    try:
        # El cliente realiza una peticion DELETE al endpoint para que el equipo abandone la liga
        # se pasa direccion y headers de atentificacion de usuario inscripto, guardando la respuesta en `r`
        r = client.delete(url(liga.league_id, inscripto.team_id), headers=headers(inscripto))
        assert r.status_code == 204
        # La salida fue exitosa, por lo que debe llegar un único evento.
        eventos = [queue.get_nowait() for _ in range(queue.qsize())]
    finally: # aseguro que se desuscriba del bus aunque falle el test, para no afectar otros tests
        event_bus.unsubscribe(queue)

    assert eventos == [{
        "event": "LEAGUE_TEAM_LEFT",
        "data": {"league_id": liga.league_id, "team_id": inscripto.team_id},
    }]

