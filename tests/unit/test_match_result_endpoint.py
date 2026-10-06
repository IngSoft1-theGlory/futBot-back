"""
Tests del endpoint GET /api/v1/matches/{match_id}/result (resultado final de un partido)
y de get_match_result (service).

Los del endpoint pasan por HTTP de verdad (TestClient): ruta + service + base juntos.
Un error se identifica por el campo "error" del JSON, no solo por el número HTTP.
"""

import pytest

from src.core.exceptions import MatchNotFinishedError, MatchNotFoundError
from src.models import Match, MatchStatus, Team, User
from src.services.match_result_service import get_match_result

# Reutiliza fixtures (db, client, usuario) y helpers de los tests de amistosos
from tests.unit.test_post_friendly_endpoint import client, db, headers, usuario  # noqa: F401
from tests.unit.test_join_friendly_endpoint import rival  # noqa: F401


def url(match_id):
    return f"/api/v1/matches/{match_id}/result"


@pytest.fixture()
def terminado(db, usuario, rival):
    """Partido FINISHED: Local FC (anfitrión) 3 - 1 Rival FC (visitante)."""
    match = Match(
        team_host_id=usuario.team_id, team_away_id=rival.team_id,
        match_duration=5, status=MatchStatus.FINISHED, home_goals=3, away_goals=1,
    )
    db.add(match)
    db.commit()
    return match


# --- 200 OK ---------------------------------------------------------------------

def test_deberia_devolver_el_resultado_final_segun_el_contrato(client, usuario, rival, terminado):
    r = client.get(url(terminado.match_id), headers=headers(usuario))

    assert r.status_code == 200
    assert r.json() == {
        "match_id": terminado.match_id,
        "status": "FINISHED",
        "home_team": {"team_id": usuario.team_id, "team_name": "Local FC", "goals": 3},
        "away_team": {"team_id": rival.team_id, "team_name": "Rival FC", "goals": 1},
    }


def test_deberia_asignar_los_goles_al_equipo_correcto(client, db, usuario, rival):
    """home_goals es del anfitrión y away_goals del visitante (no se cruzan)."""
    match = Match(
        team_host_id=usuario.team_id, team_away_id=rival.team_id,
        match_duration=5, status=MatchStatus.FINISHED, home_goals=0, away_goals=7,
    )
    db.add(match)
    db.commit()

    data = client.get(url(match.match_id), headers=headers(usuario)).json()

    assert data["home_team"]["team_id"] == usuario.team_id
    assert data["home_team"]["goals"] == 0
    assert data["away_team"]["team_id"] == rival.team_id
    assert data["away_team"]["goals"] == 7


def test_deberia_devolver_goles_en_cero_en_un_0_a_0(client, db, usuario, rival):
    """Un empate sin goles es un resultado válido: el 0 no se omite."""
    match = Match(
        team_host_id=usuario.team_id, team_away_id=rival.team_id,
        match_duration=5, status=MatchStatus.FINISHED,
    )
    db.add(match)
    db.commit()

    data = client.get(url(match.match_id), headers=headers(usuario)).json()

    assert data["home_team"]["goals"] == 0
    assert data["away_team"]["goals"] == 0


def test_deberia_devolver_solo_los_campos_del_contrato(client, usuario, terminado):
    data = client.get(url(terminado.match_id), headers=headers(usuario)).json()

    assert set(data) == {"match_id", "status", "home_team", "away_team"}
    assert set(data["home_team"]) == {"team_id", "team_name", "goals"}
    assert set(data["away_team"]) == {"team_id", "team_name", "goals"}


def test_cualquier_usuario_autenticado_puede_ver_el_resultado(client, db, terminado):
    """Sin 403 en el contrato: no hace falta haber jugado el partido."""
    otro = User(username="neymar", email="ney@example.com", password_hash="x", team=Team(team_name="Otro FC"))
    db.add(otro)
    db.commit()

    r = client.get(url(terminado.match_id), headers=headers(otro))

    assert r.status_code == 200


# --- 400 MATCH_NOT_FINISHED -----------------------------------------------------

@pytest.mark.parametrize("estado", [MatchStatus.PENDING, MatchStatus.IN_PROGRESS])
def test_deberia_devolver_400_match_not_finished_si_el_partido_no_termino(client, db, usuario, rival, estado):
    away = rival.team_id if estado == MatchStatus.IN_PROGRESS else None  # PENDING no tiene visitante
    match = Match(
        team_host_id=usuario.team_id, team_away_id=away,
        match_duration=5, status=estado, home_goals=2, away_goals=2,
    )
    db.add(match)
    db.commit()

    r = client.get(url(match.match_id), headers=headers(usuario))

    assert r.status_code == 400
    assert r.json() == {
        "error": "MATCH_NOT_FINISHED",
        "message": "El resultado final aún no está disponible.",
    }


# --- 404 MATCH_NOT_FOUND --------------------------------------------------------

def test_deberia_devolver_404_match_not_found_con_partido_inexistente(client, usuario):
    r = client.get(url(999), headers=headers(usuario))

    assert r.status_code == 404
    assert r.json() == {"error": "MATCH_NOT_FOUND", "message": "El partido solicitado no existe."}


# --- 401 UNAUTHORIZED -----------------------------------------------------------

def test_deberia_devolver_401_sin_token(client, terminado):
    r = client.get(url(terminado.match_id))

    assert r.status_code == 401
    assert r.json()["error"] == "UNAUTHORIZED"


def test_deberia_devolver_401_con_token_invalido(client, terminado):
    r = client.get(url(terminado.match_id), headers={"Authorization": "Bearer token-falso"})

    assert r.status_code == 401
    assert r.json()["error"] == "UNAUTHORIZED"


def test_deberia_pedir_autenticacion_antes_de_buscar_el_partido(client):
    """Sin token y con un partido inexistente: 401 (no 404), para no revelar qué ids existen."""
    r = client.get(url(999))

    assert r.status_code == 401


# --- 422 VALIDATION_ERROR -------------------------------------------------------

def test_deberia_devolver_422_si_match_id_no_es_un_entero(client, usuario):
    r = client.get("/api/v1/matches/abc/result", headers=headers(usuario))

    assert r.status_code == 422
    assert r.json()["error"] == "VALIDATION_ERROR"


# --- Service: get_match_result (con la fixture `session` de conftest) -----------

def _equipos(session):
    host, away = Team(team_name="Host FC"), Team(team_name="Away FC")
    session.add_all([host, away])
    session.commit()
    return host, away


def test_service_deberia_devolver_el_partido_si_esta_finished(session):
    host, away = _equipos(session)
    match = Match(team_host_id=host.team_id, team_away_id=away.team_id,
                  match_duration=5, status=MatchStatus.FINISHED, home_goals=2, away_goals=1)
    session.add(match)
    session.commit()

    resultado = get_match_result(session, match.match_id)

    assert resultado.match_id == match.match_id
    assert (resultado.home_goals, resultado.away_goals) == (2, 1)


def test_service_deberia_lanzar_match_not_found_si_no_existe(session):
    with pytest.raises(MatchNotFoundError):
        get_match_result(session, 12345)


def test_service_deberia_lanzar_match_not_finished_si_esta_en_curso(session):
    host, away = _equipos(session)
    match = Match(team_host_id=host.team_id, team_away_id=away.team_id,
                  match_duration=5, status=MatchStatus.IN_PROGRESS)
    session.add(match)
    session.commit()

    with pytest.raises(MatchNotFinishedError):
        get_match_result(session, match.match_id)
