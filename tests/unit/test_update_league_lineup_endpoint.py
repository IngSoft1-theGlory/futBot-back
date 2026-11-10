"""
Tests del endpoint PUT /api/v1/leagues/{league_id}/teams/{team_id}/lineup (cambiar la alineación en una liga).
"""

import pytest
from sqlalchemy import select

from src.models import League, LeagueStatus, LineupEntry, Team, User

from tests.unit.test_post_friendly_endpoint import (
    client, comportamiento, crear_jugadores, db, headers, usuario
)


def url(league_id, team_id):
    return f"/api/v1/leagues/{league_id}/teams/{team_id}/lineup"


def nueva_alineacion(jugadores, behavior_id):
    """Formación 1-2: los que eran suplentes pasan a titulares y al revés."""
    roles = ["DEFENDER", "FORWARD_LEFT", "FORWARD_RIGHT"]
    return {
        "formation_type": "1-2",
        "starting_players": [
            {"player_id": j.player_id, "role": rol, "behavior_id": behavior_id}
            for j, rol in zip(jugadores[3:], roles)
        ],
        "substitute_players": [
            {"player_id": j.player_id, "behavior_id": behavior_id} for j in jugadores[:3]
        ],
    }


def roles_guardados(db, liga, team_id):
    roles = db.scalars(
        select(LineupEntry.role).where(LineupEntry.league_id == liga.league_id, LineupEntry.team_id == team_id)
    )
    return sorted(rol for rol in roles if rol is not None)


@pytest.fixture()
def jugadores(db, usuario):
    return crear_jugadores(db, usuario.team)


@pytest.fixture()
def liga(db, usuario, jugadores, comportamiento):
    """Liga con el equipo de `usuario` inscripto en formación 2-1."""
    liga = League(league_name="Copa", max_teams=8, match_duration=5, host_team_id=usuario.team_id)
    db.add(liga)
    db.commit()
    roles = ["DEF_LEFT", "DEF_RIGHT", "FORWARD", None, None, None]
    db.add_all(
        LineupEntry(
            league_id=liga.league_id, team_id=usuario.team_id, player_id=j.player_id,
            behavior_id=comportamiento.behavior_id, role=rol, is_starter=rol is not None,
        )
        for j, rol in zip(jugadores, roles)
    )
    db.commit()
    return liga


@pytest.fixture()
def otro_usuario(db):
    user = User(username="cr7", email="cr7@example.com", password_hash="hash-falso", team=Team(team_name="Rival FC"))
    db.add(user)
    db.commit()
    return user


def test_deberia_reemplazar_la_alineacion_y_devolverla(client, db, usuario, jugadores, liga, comportamiento):
    liga.status = LeagueStatus.IN_PROGRESS
    db.commit()
    body = nueva_alineacion(jugadores, comportamiento.behavior_id)

    r = client.put(url(liga.league_id, usuario.team_id), json=body, headers=headers(usuario))

    assert r.status_code == 200
    assert r.json() == {"league_id": liga.league_id, "team_id": usuario.team_id, **body}
    assert roles_guardados(db, liga, usuario.team_id) == ["DEFENDER", "FORWARD_LEFT", "FORWARD_RIGHT"]


def test_deberia_responder_400_y_mantener_la_anterior_si_la_alineacion_es_invalida(client, db, usuario, jugadores, liga, comportamiento):
    body = nueva_alineacion(jugadores, comportamiento.behavior_id)
    body["formation_type"] = "2-1"  # los roles no corresponden a esta formación

    r = client.put(url(liga.league_id, usuario.team_id), json=body, headers=headers(usuario))

    assert r.status_code == 400
    assert r.json()["error"] == "INVALID_CONFIGURATION"
    assert roles_guardados(db, liga, usuario.team_id) == ["DEF_LEFT", "DEF_RIGHT", "FORWARD"]


def test_deberia_responder_409_si_la_liga_ya_termino(client, db, usuario, jugadores, liga, comportamiento):
    liga.status = LeagueStatus.FINISHED
    db.commit()

    r = client.put(url(liga.league_id, usuario.team_id), json=nueva_alineacion(jugadores, comportamiento.behavior_id), headers=headers(usuario))

    assert r.status_code == 409
    assert r.json()["error"] == "LEAGUE_FINISHED"


def test_deberia_responder_403_si_el_equipo_no_es_del_usuario(client, usuario, jugadores, liga, comportamiento, otro_usuario):
    r = client.put(url(liga.league_id, usuario.team_id), json=nueva_alineacion(jugadores, comportamiento.behavior_id), headers=headers(otro_usuario))

    assert r.status_code == 403
    assert r.json()["error"] == "UNAUTHORIZED_ACTION"


def test_deberia_responder_404_si_la_liga_no_existe(client, usuario, jugadores, comportamiento):
    r = client.put(url(9999, usuario.team_id), json=nueva_alineacion(jugadores, comportamiento.behavior_id), headers=headers(usuario))

    assert r.status_code == 404
    assert r.json()["error"] == "LEAGUE_NOT_FOUND"


def test_deberia_responder_404_si_el_equipo_no_esta_inscripto(client, db, liga, comportamiento, otro_usuario):
    jugadores_rival = crear_jugadores(db, otro_usuario.team)

    r = client.put(url(liga.league_id, otro_usuario.team_id), json=nueva_alineacion(jugadores_rival, comportamiento.behavior_id), headers=headers(otro_usuario))

    assert r.status_code == 404
    assert r.json()["error"] == "TEAM_NOT_IN_LEAGUE"
