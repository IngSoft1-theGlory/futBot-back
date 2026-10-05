"""
Tests del endpoint GET /api/v1/friendly/{match_id} (estado del lobby de un amistoso).

Pasan por HTTP de verdad (TestClient): ruta + service + base juntos.
"""

import pytest

from src.models import Match, MatchStatus, Team, User

# Reutiliza fixtures (db, client, usuario, comportamiento) y helpers de los tests de amistosos
from tests.unit.test_post_friendly_endpoint import (  # noqa: F401
    client, comportamiento, db, headers, usuario,
)
from tests.unit.test_join_friendly_endpoint import body_rival, motor_lanzado, partido, rival  # noqa: F401


def url(match_id):
    return f"/api/v1/friendly/{match_id}"


def test_deberia_devolver_pending_con_team_away_null_si_no_hay_rival(client, usuario, partido):
    r = client.get(url(partido.match_id), headers=headers(usuario))

    assert r.status_code == 200
    assert r.json() == {
        "match_id": partido.match_id,
        "status": "PENDING",
        "match_duration": 5,
        "team_host": {"team_id": usuario.team_id, "team_name": "Local FC", "team_logo": None},
        "team_away": None,
    }


def test_deberia_devolver_in_progress_con_ambos_equipos_si_hay_rival(client, db, usuario, rival):
    match = Match(
        team_host_id=usuario.team_id, team_away_id=rival.team_id,
        match_duration=7, status=MatchStatus.IN_PROGRESS,
    )
    db.add(match)
    db.commit()

    r = client.get(url(match.match_id), headers=headers(usuario))

    assert r.status_code == 200
    assert r.json() == {
        "match_id": match.match_id,
        "status": "IN_PROGRESS",
        "match_duration": 7,
        "team_host": {"team_id": usuario.team_id, "team_name": "Local FC", "team_logo": None},
        "team_away": {"team_id": rival.team_id, "team_name": "Rival FC", "team_logo": None},
    }


def test_deberia_devolver_in_progress_despues_de_que_se_une_el_rival(
    client, db, usuario, rival, comportamiento, partido
):
    antes = client.get(url(partido.match_id), headers=headers(usuario))
    assert antes.json()["status"] == "PENDING"

    union = client.post(
        f"{url(partido.match_id)}/teams",
        json=body_rival(rival, db, comportamiento),
        headers=headers(rival),
    )
    assert union.status_code == 200

    despues = client.get(url(partido.match_id), headers=headers(usuario))
    assert despues.status_code == 200
    assert despues.json()["status"] == "IN_PROGRESS"
    assert despues.json()["team_away"]["team_id"] == rival.team_id
    assert despues.json()["team_away"]["team_name"] == "Rival FC"


def test_cualquier_usuario_autenticado_puede_ver_el_amistoso(client, db, partido):
    otro = User(username="neymar", email="ney@example.com", password_hash="x", team=Team(team_name="Otro FC"))
    db.add(otro)
    db.commit()

    r = client.get(url(partido.match_id), headers=headers(otro))

    assert r.status_code == 200


def test_deberia_devolver_404_match_not_found_con_partido_inexistente(client, usuario):
    r = client.get(url(999), headers=headers(usuario))

    assert r.status_code == 404
    assert r.json()["error"] == "MATCH_NOT_FOUND"


def test_deberia_devolver_401_sin_token(client, partido):
    r = client.get(url(partido.match_id))

    assert r.status_code == 401


def test_deberia_devolver_401_con_token_invalido(client, partido):
    r = client.get(url(partido.match_id), headers={"Authorization": "Bearer token-falso"})

    assert r.status_code == 401
