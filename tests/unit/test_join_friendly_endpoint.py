"""
Tests del endpoint POST /api/v1/friendly/{match_id}/teams (unirse a un amistoso).

Pasan por HTTP de verdad (TestClient): ruta + service + base juntos.
Cada test de error parte de un body VÁLIDO y cambia UNA sola cosa.
"""

import pytest
from sqlalchemy import select

from src.models import LineupEntry, Match, MatchStatus, Team, User
from src.realtime.event_bus import event_bus

# Reutiliza fixtures (db, client, usuario, comportamiento) y helpers del test de crear amistoso
from tests.unit.test_post_friendly_endpoint import (  # noqa: F401
    armar_body, client, comportamiento, contar, crear_jugadores, db, headers, usuario,
)


def url(match_id):
    return f"/api/v1/friendly/{match_id}/teams"


@pytest.fixture()
def rival(db):
    user = User(
        username="cr7", email="cr7@example.com",
        password_hash="hash-falso", team=Team(team_name="Rival FC"),
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture()
def partido(db, usuario):
    """Amistoso PENDING creado por `usuario` (anfitrión), sin rival."""
    match = Match(team_host_id=usuario.team_id, match_duration=5, status=MatchStatus.PENDING)
    db.add(match)
    db.commit()
    return match


def body_rival(rival, db, comportamiento, **cambios):
    jugadores = crear_jugadores(db, rival.team)
    body = armar_body(rival.team, jugadores, comportamiento, **cambios)
    del body["match_duration"]
    return body


def test_deberia_unir_rival_pasar_a_in_progress_y_persistir_alineacion(
    client, db, usuario, rival, comportamiento, partido
):
    r = client.post(url(partido.match_id), json=body_rival(rival, db, comportamiento), headers=headers(rival))

    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "IN_PROGRESS"
    assert data["team_away_id"] == rival.team_id
    assert data["team_host_id"] == usuario.team_id

    db.expire_all()
    match = db.get(Match, partido.match_id)
    assert match.status == MatchStatus.IN_PROGRESS
    assert match.team_away_id == rival.team_id
    assert contar(db, LineupEntry) == 6


def test_deberia_publicar_eventos_con_el_payload_del_contrato(
    client, db, usuario, rival, comportamiento, partido
):
    queue = event_bus.subscribe()
    try:
        r = client.post(url(partido.match_id), json=body_rival(rival, db, comportamiento), headers=headers(rival))
        assert r.status_code == 200
        eventos = [queue.get_nowait() for _ in range(queue.qsize())]
    finally:
        event_bus.unsubscribe(queue)

    base = {"match_id": partido.match_id, "team_host_id": usuario.team_id, "team_away_id": rival.team_id}
    assert {"event": "GUEST_JOINED_FRIENDLY", "data": base} in eventos
    assert {"event": "MATCH_STARTED", "data": {**base, "status": "IN_PROGRESS"}} in eventos
    assert len(eventos) == 2


def test_no_deberia_publicar_eventos_si_la_union_falla(
    client, db, usuario, rival, comportamiento, partido
):
    queue = event_bus.subscribe()
    try:
        body = body_rival(rival, db, comportamiento, formation_type="9-9")
        client.post(url(partido.match_id), json=body, headers=headers(rival))
        assert queue.qsize() == 0
    finally:
        event_bus.unsubscribe(queue)


def test_deberia_devolver_400_con_alineacion_invalida_y_no_modificar_el_partido(
    client, db, usuario, rival, comportamiento, partido
):
    body = body_rival(rival, db, comportamiento, formation_type="9-9")

    r = client.post(url(partido.match_id), json=body, headers=headers(rival))

    assert r.status_code == 400
    assert r.json()["error"] == "INVALID_CONFIGURATION"
    db.expire_all()
    assert db.get(Match, partido.match_id).status == MatchStatus.PENDING
    assert contar(db, LineupEntry) == 0


def test_deberia_devolver_404_match_not_found_con_partido_inexistente(
    client, db, rival, comportamiento
):
    r = client.post(url(999), json=body_rival(rival, db, comportamiento), headers=headers(rival))

    assert r.status_code == 404
    assert r.json()["error"] == "MATCH_NOT_FOUND"


def test_deberia_devolver_409_match_unavailable_si_el_partido_ya_tiene_rival_y_no_duplicar(
    client, db, usuario, rival, comportamiento, partido
):
    otro = User(username="neymar", email="ney@example.com", password_hash="x", team=Team(team_name="Otro FC"))
    db.add(otro)
    db.commit()
    primero = client.post(url(partido.match_id), json=body_rival(otro, db, comportamiento), headers=headers(otro))
    assert primero.status_code == 200

    r = client.post(url(partido.match_id), json=body_rival(rival, db, comportamiento), headers=headers(rival))

    assert r.status_code == 409
    assert r.json()["error"] == "MATCH_UNAVAILABLE"
    db.expire_all()
    assert db.get(Match, partido.match_id).team_away_id == otro.team_id
    assert contar(db, LineupEntry) == 6  # solo la del primero que se unió


def test_deberia_devolver_409_si_pierde_la_carrera_justo_antes_de_inscribirse(
    client, db, usuario, rival, comportamiento, partido, monkeypatch
):
    # Simula la condición de carrera: el chequeo de estado pasa, pero otro equipo
    # se llevó el cupo antes del UPDATE condicional.
    monkeypatch.setattr("src.services.friendly_service.claim_pending_match", lambda *a: False)

    r = client.post(url(partido.match_id), json=body_rival(rival, db, comportamiento), headers=headers(rival))

    assert r.status_code == 409
    assert r.json()["error"] == "MATCH_UNAVAILABLE"
    assert contar(db, LineupEntry) == 0


def test_deberia_devolver_422_precondition_failed_con_menos_de_6_jugadores(
    client, db, usuario, rival, comportamiento, partido
):
    jugadores = crear_jugadores(db, rival.team, cantidad=5)
    body = armar_body(rival.team, jugadores + [jugadores[0]], comportamiento)
    del body["match_duration"]

    r = client.post(url(partido.match_id), json=body, headers=headers(rival))

    assert r.status_code == 422
    assert r.json()["error"] == "PRECONDITION_FAILED"
    db.expire_all()
    assert db.get(Match, partido.match_id).status == MatchStatus.PENDING


def test_deberia_devolver_403_si_el_equipo_no_es_del_usuario(
    client, db, usuario, rival, comportamiento, partido
):
    body = body_rival(rival, db, comportamiento)

    r = client.post(url(partido.match_id), json=body, headers=headers(usuario))

    assert r.status_code == 403


def test_deberia_devolver_400_si_el_anfitrion_intenta_unirse_a_su_propio_partido(
    client, db, usuario, comportamiento, partido
):
    jugadores = crear_jugadores(db, usuario.team)
    body = armar_body(usuario.team, jugadores, comportamiento)
    del body["match_duration"]

    r = client.post(url(partido.match_id), json=body, headers=headers(usuario))

    assert r.status_code == 400
    assert r.json()["error"] == "INVALID_SETTINGS"


def test_deberia_devolver_401_sin_token(client, partido):
    assert client.post(url(partido.match_id), json={}).status_code == 401
