"""
Tests del endpoint POST /api/v1/friendly (crear amistoso).

Pasan por HTTP de verdad (TestClient), así que prueban ruta + service + base juntos.
Cada test de error parte de un body VÁLIDO y cambia UNA sola cosa.
Un error se identifica por el campo "error" del JSON, no solo por el número HTTP.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.security import create_access_token
from src.database.base import Base, get_db
from src.main import app
from src.models import Behavior, LineupEntry, Match, MatchStatus, Player, Team, User
from src.realtime.event_bus import event_bus

URL = "/api/v1/friendly"


# --- Base y cliente -------------------------------------------------------------
# TestClient corre la app en OTRO hilo. Una SQLite en memoria "normal" le daría una
# base vacía a ese hilo, por eso acá se usa StaticPool (una única conexión compartida).

@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys_on(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def client(db):
    # Reemplaza get_db: la app usa la MISMA base de test en lugar de la real.
    def override_get_db():
        s = sessionmaker(bind=db.get_bind(), autoflush=False)()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- Datos de prueba --------------------------------------------------------------

@pytest.fixture()
def usuario(db):
    # Usuario con su equipo (User.team = Team).
    user = User(
        username="messi10", email="messi10@example.com",
        password_hash="hash-falso", team=Team(team_name="Local FC"),
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture()
def comportamiento(db):
    behavior = Behavior(name="Patear", description="Patea", code="def on_tick(api): pass", is_default=True)
    db.add(behavior)
    db.commit()
    return behavior


def crear_jugadores(db, equipo, cantidad=6):
    jugadores = [
        Player(team_id=equipo.team_id, name=f"Jugador {n}", number=n,
               power=60, agility=60, control=60, speed=60, strength=60)
        for n in range(1, cantidad + 1)
    ]
    db.add_all(jugadores)
    db.commit()
    return jugadores


def headers(user):
    # Token real firmado con la SECRET_KEY de la app, como el que daría /login.
    return {"Authorization": f"Bearer {create_access_token(user.user_id)}"}


def armar_body(equipo, jugadores, comportamiento, **cambios):
    """Body VÁLIDO (formación 2-1, 3 titulares + 3 suplentes). `cambios` pisa campos."""
    b = comportamiento.behavior_id
    body = {
        "team_id": equipo.team_id,
        "match_duration": 5,
        "formation_type": "2-1",
        "starting_players": [
            {"player_id": jugadores[0].player_id, "role": "DEF_LEFT", "behavior_id": b},
            {"player_id": jugadores[1].player_id, "role": "DEF_RIGHT", "behavior_id": b},
            {"player_id": jugadores[2].player_id, "role": "FORWARD", "behavior_id": b},
        ],
        "substitute_players": [
            {"player_id": j.player_id, "behavior_id": b} for j in jugadores[3:6]
        ],
    }
    body.update(cambios)
    return body


def contar(db, modelo):
    return db.scalar(select(func.count()).select_from(modelo))


# Caso exitoso 

def test_deberia_crear_amistoso_pending_y_persistir_partido_y_alineacion(
    client, db, usuario, comportamiento
):
    equipo = usuario.team
    jugadores = crear_jugadores(db, equipo)

    r = client.post(URL, json=armar_body(equipo, jugadores, comportamiento), headers=headers(usuario))

    assert r.status_code == 201
    data = r.json()
    # La respuesta tiene exactamente estos campos (sin alineación ni team_away_id).
    assert set(data) == {"match_id", "team_host_id", "status", "match_duration"}
    assert data["status"] == "PENDING"
    assert data["team_host_id"] == equipo.team_id
    assert data["match_duration"] == 5

    # Y quedó guardado: 1 partido PENDING sin rival + 6 entries de ese equipo.
    match = db.scalars(select(Match)).one()
    assert match.status == MatchStatus.PENDING
    assert match.team_away_id is None
    assert contar(db, LineupEntry) == 6


# Casos de error 

@pytest.mark.parametrize("duracion", [0, -5, 11])
def test_deberia_devolver_400_invalid_settings_y_no_persistir_con_duracion_invalida(
    client, db, usuario, comportamiento, duracion
):
    jugadores = crear_jugadores(db, usuario.team)
    body = armar_body(usuario.team, jugadores, comportamiento, match_duration=duracion)

    r = client.post(URL, json=body, headers=headers(usuario))

    assert r.status_code == 400
    assert r.json()["error"] == "INVALID_SETTINGS"
    assert contar(db, Match) == 0
    assert contar(db, LineupEntry) == 0


def test_deberia_devolver_400_invalid_configuration_y_no_persistir_con_formacion_inexistente(
    client, db, usuario, comportamiento
):
    jugadores = crear_jugadores(db, usuario.team)
    body = armar_body(usuario.team, jugadores, comportamiento, formation_type="9-9")

    r = client.post(URL, json=body, headers=headers(usuario))

    assert r.status_code == 400
    assert r.json()["error"] == "INVALID_CONFIGURATION"
    assert contar(db, Match) == 0
    assert contar(db, LineupEntry) == 0


def test_deberia_devolver_400_invalid_configuration_y_no_persistir_con_jugador_repetido(
    client, db, usuario, comportamiento
):
    jugadores = crear_jugadores(db, usuario.team)
    body = armar_body(usuario.team, jugadores, comportamiento)
    # El 2do titular pasa a ser el mismo jugador que el 1ro.
    body["starting_players"][1]["player_id"] = jugadores[0].player_id

    r = client.post(URL, json=body, headers=headers(usuario))

    assert r.status_code == 400
    assert r.json()["error"] == "INVALID_CONFIGURATION"
    assert contar(db, Match) == 0
    assert contar(db, LineupEntry) == 0


def test_deberia_devolver_422_precondition_failed_con_menos_de_6_jugadores(
    client, db, usuario, comportamiento
):
    jugadores = crear_jugadores(db, usuario.team, cantidad=5)
    # La alineación necesita 6 lugares: repito un jugador solo para armar el body.
    # No importa: el mínimo de jugadores se chequea ANTES que la alineación.
    body = armar_body(usuario.team, jugadores + [jugadores[0]], comportamiento)

    r = client.post(URL, json=body, headers=headers(usuario))

    assert r.status_code == 422
    assert r.json()["error"] == "PRECONDITION_FAILED"
    assert contar(db, Match) == 0


def test_deberia_devolver_403_y_no_persistir_si_el_equipo_es_de_otro_usuario(
    client, db, usuario, comportamiento
):
    ajeno = Team(team_name="Equipo Ajeno")
    db.add(ajeno)
    db.commit()
    jugadores = crear_jugadores(db, ajeno)

    r = client.post(URL, json=armar_body(ajeno, jugadores, comportamiento), headers=headers(usuario))

    assert r.status_code == 403
    assert contar(db, Match) == 0

# tests evento de creación de amistoso

def test_deberia_publicar_friendly_created_con_el_payload_del_contrato(
    client, db, usuario, comportamiento
):
    jugadores = crear_jugadores(db, usuario.team)
    queue = event_bus.subscribe()
    try:
        r = client.post(URL, json=armar_body(usuario.team, jugadores, comportamiento), headers=headers(usuario))
        assert r.status_code == 201
        eventos = [queue.get_nowait() for _ in range(queue.qsize())]
    finally:
        event_bus.unsubscribe(queue)

    assert eventos == [{
        "event": "FRIENDLY_CREATED",
        "data": {
            "match_id": r.json()["match_id"],
            "team_host_id": usuario.team_id,
            "match_duration": 5,
            "status": "PENDING",
        },
    }]


def test_no_deberia_publicar_eventos_si_la_creacion_falla(
    client, db, usuario, comportamiento
):
    jugadores = crear_jugadores(db, usuario.team)
    body = armar_body(usuario.team, jugadores, comportamiento, formation_type="9-9")
    queue = event_bus.subscribe()
    try:
        client.post(URL, json=body, headers=headers(usuario))
        assert queue.qsize() == 0
    finally:
        event_bus.unsubscribe(queue)