"""
Test de punta a punta: unirse a un amistoso -> prepare_match + launch_match ->
motor real corriendo -> partido FINISHED -> goles guardados.

Va por HTTP (httpx sobre la app, dentro del event loop del test, así la tarea del
motor corre de verdad). El guardado del resultado y el reloj se inyectan con
dependency_overrides de get_launch_options: nada toca SessionLocal/Postgres.
"""

import asyncio

import httpx
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from src.database.base import Base, get_db

from src.database.base import get_db
from src.engine._02_to_match.state import MatchPhase, MatchRegistry
from src.engine._01_to_world.pitch import TeamSide
from src.main import app
from src.models import Match, MatchStatus
from src.routes.friendly import get_launch_options
from src.services import match_start_service
from src.services.match_start_service import make_on_finished

from tests.unit.test_join_friendly_endpoint import body_rival, partido, rival  
from tests.unit.test_post_friendly_endpoint import (
    comportamiento, headers, usuario,
)

CORRER_A_LA_PELOTA = """
def on_tick(api):
    api.run_to(api.get_game_state().ball_position, 1.0)
"""

@pytest.fixture()
def db(tmp_path):
    """Base SQLite temporal y exclusiva para este test.
    Se usa un archivo para permitir varias conexiones independientes."""

    # Crea la base SQLite temporal para este test.
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )

    # Activa la validación de claves foráneas en SQLite.
    @event.listens_for(engine, "connect")
    def _foreign_keys_on(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    # Crea las tablas definidas por los modelos.
    Base.metadata.create_all(engine)

    # Crea la sesión que usará el test para leer y guardar datos.
    session = sessionmaker(bind=engine, autoflush=False)()

    # Entrega la sesión al test.
    yield session

    session.close()
    engine.dispose()

@pytest.fixture()
def app_con_motor_aislado(db):
    """Misma base de test para el request y para el guardado del resultado; ticks instantáneos."""
    sesiones = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    observado = {"estados": [], "registry": MatchRegistry()}

    async def notify(state):
        observado["estados"].append(state)

    # el mismo estado cambia en cada tick: guardo la foto de las posiciones del primero y del último
    posiciones = {}

    async def notify_con_fotos(state):
        fotos = {pid: p.position for pid, p in state.players.items() if p.position is not None}
        posiciones.setdefault("inicial", fotos)
        posiciones["final"] = fotos
        await notify(state)

    goles = iter([TeamSide.HOME, TeamSide.HOME, TeamSide.AWAY])

    def detect_goal(_ball_position):
        return next(goles, None)

    def get_db_de_test():
        s = sesiones()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = get_db_de_test
    app.dependency_overrides[get_launch_options] = lambda: {
        "on_finished": make_on_finished(sesiones),
        "notify": notify_con_fotos,
        "detect_goal": detect_goal,
        "registry": observado["registry"],
        "tick_interval_seconds": 0,
    }
    observado["posiciones"] = posiciones
    yield observado
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_deberia_unirse_correr_el_partido_hasta_finished_y_guardar_los_goles(
    db, usuario, rival, comportamiento, partido, app_con_motor_aislado
):
    comportamiento.code = CORRER_A_LA_PELOTA
    db.commit()
    body = body_rival(rival, db, comportamiento)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(f"/api/v1/friendly/{partido.match_id}/teams", json=body, headers=headers(rival))
    assert r.status_code == 200
    assert r.json()["status"] == "IN_PROGRESS"

    # el motor corre como tarea de fondo: espero a que termine
    await asyncio.wait_for(asyncio.gather(*match_start_service._running_matches), timeout=30)

    estados = app_con_motor_aislado["estados"]
    assert len(estados) == 600  # 5 minutos a 2 ticks por segundo
    assert estados[-1].phase is MatchPhase.FINISHED
    assert partido.match_id not in app_con_motor_aislado["registry"]  # liberado al terminar

    # los goles se guardaron y el partido quedó FINISHED en la base
    db.expire_all()
    guardado = db.get(Match, partido.match_id)
    assert guardado.status is MatchStatus.FINISHED
    assert (guardado.home_goals, guardado.away_goals) == (2, 1)

    # los PACSS llegaron al motor: los jugadores en cancha se movieron
    inicial = app_con_motor_aislado["posiciones"]["inicial"]
    final = app_con_motor_aislado["posiciones"]["final"]
    movidos = [pid for pid in inicial if final[pid] != inicial[pid]]
    assert len(movidos) == 6
