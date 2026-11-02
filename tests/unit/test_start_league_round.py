"""
Tests de start_league_round: arrancar todos los partidos de una fecha de la liga.

Se usa el motor real: un partido con el motor corriendo aparece en match_registry.
Al terminar cada test los motores se cancelan, asi que nunca llegan a guardar un resultado.

- Primero se prueba la funcion sola, con la sesion de test.
- Despues se prueba por HTTP que el PUT y la inscripcion la llamen, como en produccion.
"""

import asyncio

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from src.core.security import get_current_user
from src.database.base import get_db
from src.engine._02_to_match.state import match_registry
from src.main import app
from src.models import Behavior, League, LeagueStatus, Match, MatchStatus, Team
from src.realtime.event_bus import event_bus
from src.repositories.match_repository import get_lineup_entries, get_pending_round_matches
from src.services import league_run_service, match_start_service
from src.services.fixture_service import generate_fixture
from src.services.league_run_service import start_league_round

from tests.unit.test_join_friendly_motor import db
from tests.unit.test_join_league_service import armar_body, crear_jugadores, crear_usuario
from tests.unit.test_launch_league_match import CODIGO_VALIDO, _alinear_en_la_liga


@pytest.fixture(autouse=True)
def logger_encendido(monkeypatch):
    """test_alembic_migrations corre alembic/env.py, que apaga los loggers que ya existen.
    Si ese test corrio antes en el mismo proceso, caplog quedaria vacio."""
    monkeypatch.setattr(league_run_service.logger, "disabled", False)


@pytest_asyncio.fixture()
async def frenar_motores():
    """Al terminar el test cancela los motores que quedaron corriendo."""
    yield
    tareas = list(match_start_service._running_matches)
    for tarea in tareas:
        tarea.cancel()
    await asyncio.gather(*tareas, return_exceptions=True)


@pytest.fixture()
def cola():
    """Cola suscripta al bus de eventos, para ver que se publico."""
    cola_de_eventos = event_bus.subscribe()
    yield cola_de_eventos
    event_bus.unsubscribe(cola_de_eventos)


def _nombres_de_eventos(cola):
    return [cola.get_nowait()["event"] for _ in range(cola.qsize())]


def _armar_liga_iniciada(session):
    """Liga de 4 equipos alineados, ya iniciada: 3 fechas de 2 partidos, todos PENDING."""
    comportamiento = Behavior(name="Quieto", description="No hace nada", code=CODIGO_VALIDO, is_default=True)
    equipos = [Team(team_name=f"Equipo {numero}") for numero in range(1, 5)]
    session.add_all([comportamiento, *equipos])
    session.flush()

    liga = League(
        league_name="Liga", max_teams=4, match_duration=2,
        host_team_id=equipos[0].team_id, status=LeagueStatus.IN_PROGRESS,
    )
    session.add(liga)
    session.flush()

    for equipo in equipos:
        _alinear_en_la_liga(session, liga, equipo, comportamiento)
    session.flush()  # generate_fixture busca los equipos en la base

    generate_fixture(session, liga)
    session.commit()
    return liga


def _partidos_de_la_fecha(session, liga, numero_de_fecha):
    session.expire_all()  # para leer lo que quedo guardado, no lo que recuerda la sesion
    return session.scalars(
        select(Match)
        .where(Match.league_id == liga.league_id, Match.round_number == numero_de_fecha)
        .order_by(Match.match_id)
    ).all()


def _romper_alineacion(session, liga, team_id):
    """Le da al equipo un comportamiento sin on_tick: sus partidos no se van a poder preparar."""
    roto = Behavior(name="Roto", description="No define on_tick", code="x = 1", is_default=True)
    session.add(roto)
    session.flush()
    for entrada in get_lineup_entries(session, league_id=liga.league_id, team_id=team_id):
        entrada.behavior_id = roto.behavior_id
    session.commit()


def _assert_solo_la_fecha_1_en_juego(session, liga):
    for partido in _partidos_de_la_fecha(session, liga, 1):
        assert partido.status is MatchStatus.IN_PROGRESS
        assert partido.match_id in match_registry  # el motor esta corriendo

    for numero_de_fecha in (2, 3):
        for partido in _partidos_de_la_fecha(session, liga, numero_de_fecha):
            assert partido.status is MatchStatus.PENDING
            assert partido.match_id not in match_registry


def test_deberia_traer_solo_los_partidos_pendientes_de_esa_liga_y_esa_fecha(session):
    liga = _armar_liga_iniciada(session)
    primero, segundo = _partidos_de_la_fecha(session, liga, 1)
    segundo.status = MatchStatus.IN_PROGRESS  # ya arranco: no tiene que venir

    # un partido de la misma fecha pero de otra liga: tampoco tiene que venir
    otra_liga = League(league_name="Otra", max_teams=4, match_duration=2, host_team_id=primero.team_host_id)
    session.add(otra_liga)
    session.flush()
    session.add(Match(
        league_id=otra_liga.league_id, round_number=1, match_duration=2, status=MatchStatus.PENDING,
        team_host_id=primero.team_host_id, team_away_id=primero.team_away_id,
    ))
    session.commit()

    pendientes = get_pending_round_matches(session, liga.league_id, 1)

    assert [partido.match_id for partido in pendientes] == [primero.match_id]


@pytest.mark.asyncio
async def test_deberia_arrancar_los_partidos_de_la_fecha_y_dejar_pendientes_los_demas(session, frenar_motores):
    liga = _armar_liga_iniciada(session)

    await start_league_round(session, liga.league_id, 1)
    await asyncio.sleep(0)  # le doy el turno a las tareas de los motores para que empiecen

    _assert_solo_la_fecha_1_en_juego(session, liga)


@pytest.mark.asyncio
async def test_deberia_arrancar_los_demas_si_un_partido_no_se_puede_preparar(session, caplog, frenar_motores):
    liga = _armar_liga_iniciada(session)
    roto, sano = _partidos_de_la_fecha(session, liga, 1)
    _romper_alineacion(session, liga, roto.team_host_id)

    await start_league_round(session, liga.league_id, 1)
    await asyncio.sleep(0)

    roto, sano = _partidos_de_la_fecha(session, liga, 1)
    assert roto.status is MatchStatus.FINISHED
    assert (roto.home_goals, roto.away_goals) == (0, 0)
    assert sano.status is MatchStatus.IN_PROGRESS
    assert sano.match_id in match_registry
    assert f"El partido {roto.match_id} no se pudo preparar" in caplog.text


@pytest.mark.asyncio
async def test_deberia_arrancar_los_demas_aunque_el_error_rompa_la_sesion(session, monkeypatch, caplog, frenar_motores):
    liga = _armar_liga_iniciada(session)
    fallido, _ = _partidos_de_la_fecha(session, liga, 1)
    id_fallido = fallido.match_id
    arrancar_de_verdad = league_run_service.start_league_match

    async def arrancar_fallando_el_primero(sesion, match_id):
        if match_id == id_fallido:
            sesion.add(Match(match_duration=2))  # sin anfitrion: el flush falla y la sesion queda rota hasta un rollback
            sesion.flush()
        await arrancar_de_verdad(sesion, match_id)

    monkeypatch.setattr(league_run_service, "start_league_match", arrancar_fallando_el_primero)

    await start_league_round(session, liga.league_id, 1)
    await asyncio.sleep(0)

    fallido, sano = _partidos_de_la_fecha(session, liga, 1)
    assert fallido.status is MatchStatus.PENDING
    assert sano.status is MatchStatus.IN_PROGRESS
    assert sano.match_id in match_registry
    assert f"No se pudo arrancar el partido {id_fallido}" in caplog.text


@pytest.mark.asyncio
async def test_no_deberia_relanzar_los_partidos_si_se_arranca_dos_veces_la_misma_fecha(
    session, cola, caplog, frenar_motores
):
    liga = _armar_liga_iniciada(session)

    await start_league_round(session, liga.league_id, 1)
    await start_league_round(session, liga.league_id, 1)

    assert _nombres_de_eventos(cola).count("MATCH_STARTED") == 2  # uno por partido, no dos
    for partido in _partidos_de_la_fecha(session, liga, 1):
        assert len(get_lineup_entries(session, match_id=partido.match_id)) == 12  # no duplico la alineacion
    assert "No se pudo arrancar" not in caplog.text


@pytest.mark.asyncio
async def test_no_deberia_lanzar_error_si_falla_la_busqueda_de_partidos(monkeypatch, caplog):
    def busqueda_que_falla(*args):
        raise RuntimeError("se cayo la base")

    monkeypatch.setattr(league_run_service, "get_pending_round_matches", busqueda_que_falla)

    await start_league_round(None, 7, 1)

    assert "No se pudieron buscar los partidos de la fecha 1 de la liga 7" in caplog.text


# --- por HTTP: el PUT y la inscripcion llaman a start_league_round ---


@pytest.fixture()
def usuario_logueado():
    """Guarda el usuario que hace el pedido: la ruta lo recibe como si viniera del token."""
    logueado = {}
    app.dependency_overrides[get_current_user] = lambda: logueado["user_id"]
    yield logueado
    app.dependency_overrides.pop(get_current_user)


@pytest.fixture()
def cliente(db, usuario_logueado):
    """Cada pedido usa su propia sesion con expire_on_commit=False, igual que en produccion."""
    sesiones = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)

    def get_db_de_test():
        with sesiones() as sesion:
            yield sesion

    app.dependency_overrides[get_db] = get_db_de_test
    yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    app.dependency_overrides.pop(get_db)


def _armar_lobby(db, equipos_inscriptos):
    """Liga PENDING de 4 lugares con equipos alineados. Devuelve la liga y sus usuarios."""
    comportamiento = Behavior(name="Quieto", description="No hace nada", code=CODIGO_VALIDO, is_default=True)
    db.add(comportamiento)
    db.flush()

    usuarios = [crear_usuario(db, f"usuario{numero}") for numero in range(equipos_inscriptos)]
    liga = League(league_name="Liga", max_teams=4, match_duration=2, host_team_id=usuarios[0].team_id)
    db.add(liga)
    db.flush()

    for usuario in usuarios:
        _alinear_en_la_liga(db, liga, usuario, comportamiento)
    db.commit()
    return liga, usuarios


@pytest.mark.asyncio
async def test_deberia_arrancar_la_fecha_1_al_iniciar_la_liga_con_el_put(
    db, cliente, usuario_logueado, cola, frenar_motores
):
    liga, usuarios = _armar_lobby(db, equipos_inscriptos=4)
    usuario_logueado["user_id"] = usuarios[0].user_id

    respuesta = await cliente.put(f"/api/v1/leagues/{liga.league_id}", json={"status": "IN_PROGRESS"})
    await asyncio.sleep(0)

    assert respuesta.status_code == 200
    _assert_solo_la_fecha_1_en_juego(db, liga)
    assert _nombres_de_eventos(cola) == ["LEAGUE_INITIATED", "MATCH_STARTED", "MATCH_STARTED"]


@pytest.mark.asyncio
async def test_deberia_arrancar_la_fecha_1_cuando_la_inscripcion_completa_el_cupo(
    db, cliente, usuario_logueado, cola, frenar_motores
):
    liga, _ = _armar_lobby(db, equipos_inscriptos=3)
    ultimo = crear_usuario(db, "ultimo")
    usuario_logueado["user_id"] = ultimo.user_id
    body = armar_body(ultimo, crear_jugadores(db, ultimo.team_id))

    respuesta = await cliente.post(f"/api/v1/leagues/{liga.league_id}/teams", json=body.model_dump())
    await asyncio.sleep(0)

    assert respuesta.status_code == 201
    _assert_solo_la_fecha_1_en_juego(db, liga)
    assert _nombres_de_eventos(cola) == ["TEAM_JOINED_LEAGUE", "LEAGUE_INITIATED", "MATCH_STARTED", "MATCH_STARTED"]


@pytest.mark.asyncio
async def test_deberia_responder_igual_al_put_aunque_un_partido_no_pueda_arrancar(
    db, cliente, usuario_logueado, frenar_motores
):
    liga, usuarios = _armar_lobby(db, equipos_inscriptos=4)
    usuario_logueado["user_id"] = usuarios[0].user_id
    _romper_alineacion(db, liga, usuarios[1].team_id)

    respuesta = await cliente.put(f"/api/v1/leagues/{liga.league_id}", json={"status": "IN_PROGRESS"})

    assert respuesta.status_code == 200
    assert respuesta.json() == {"league_id": liga.league_id, "league_name": "Liga", "status": "IN_PROGRESS"}

    # el equipo roto juega un solo partido por fecha: ese se cierra 0-0 y el otro arranca
    estados = {partido.status for partido in _partidos_de_la_fecha(db, liga, 1)}
    assert estados == {MatchStatus.FINISHED, MatchStatus.IN_PROGRESS}
