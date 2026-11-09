"""
Tests del endpoint GET /api/v1/leagues/{league_id}/teams/{team_id}/lineup (ver la alineación vigente en una liga).
"""

from tests.unit.test_post_friendly_endpoint import client, comportamiento, db, headers, usuario
from tests.unit.test_update_league_lineup_endpoint import jugadores, liga, nueva_alineacion, otro_usuario, url


def test_deberia_devolver_la_alineacion_vigente(client, usuario, jugadores, liga, comportamiento):
    r = client.get(url(liga.league_id, usuario.team_id), headers=headers(usuario))

    b = comportamiento.behavior_id
    assert r.status_code == 200
    assert r.json() == {
        "league_id": liga.league_id,
        "team_id": usuario.team_id,
        "formation_type": "2-1",
        "starting_players": [
            {"player_id": jugadores[0].player_id, "role": "DEF_LEFT", "behavior_id": b},
            {"player_id": jugadores[1].player_id, "role": "DEF_RIGHT", "behavior_id": b},
            {"player_id": jugadores[2].player_id, "role": "FORWARD", "behavior_id": b},
        ],
        "substitute_players": [{"player_id": j.player_id, "behavior_id": b} for j in jugadores[3:]],
    }


def test_deberia_devolver_la_nueva_alineacion_despues_de_cambiarla(client, usuario, jugadores, liga, comportamiento):
    body = nueva_alineacion(jugadores, comportamiento.behavior_id)
    client.put(url(liga.league_id, usuario.team_id), json=body, headers=headers(usuario))

    r = client.get(url(liga.league_id, usuario.team_id), headers=headers(usuario))

    assert r.status_code == 200
    assert r.json() == {"league_id": liga.league_id, "team_id": usuario.team_id, **body}


def test_deberia_responder_403_si_el_equipo_no_es_del_usuario(client, usuario, liga, otro_usuario):
    r = client.get(url(liga.league_id, usuario.team_id), headers=headers(otro_usuario))

    assert r.status_code == 403
    assert r.json()["error"] == "UNAUTHORIZED_ACTION"


def test_deberia_responder_404_si_la_liga_no_existe(client, usuario):
    r = client.get(url(9999, usuario.team_id), headers=headers(usuario))

    assert r.status_code == 404
    assert r.json()["error"] == "LEAGUE_NOT_FOUND"


def test_deberia_responder_404_si_el_equipo_no_esta_inscripto(client, liga, otro_usuario):
    r = client.get(url(liga.league_id, otro_usuario.team_id), headers=headers(otro_usuario))

    assert r.status_code == 404
    assert r.json()["error"] == "TEAM_NOT_IN_LEAGUE"


def test_deberia_responder_401_sin_sesion(client, usuario, liga):
    r = client.get(url(liga.league_id, usuario.team_id))

    assert r.status_code == 401
