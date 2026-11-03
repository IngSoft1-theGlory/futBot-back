"""
Tests de start_league_round: arrancar todos los partidos de una fecha de la liga.

Se usa el motor real: un partido con el motor corriendo aparece en match_registry.
Al terminar cada test los motores se cancelan, asi que nunca llegan a guardar un resultado.
"""

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import select

from src.engine._02_to_match.state import match_registry
from src.models import Behavior, League, LeagueStatus, Match, MatchStatus, Team
from src.realtime.event_bus import event_bus
from src.repositories.match_repository import get_lineup_entries
from src.services import league_run_service, match_start_service
from src.services.fixture_service import generate_fixture
from src.services.league_run_service import start_league_round

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


@pytest.mark.asyncio
async def test_deberia_arrancar_los_partidos_de_la_fecha_y_dejar_pendientes_los_demas(session, frenar_motores):
    liga = _armar_liga_iniciada(session)

    await start_league_round(session, liga.league_id, 1)
    await asyncio.sleep(0)  # le doy el turno a las tareas de los motores para que empiecen

    for partido in _partidos_de_la_fecha(session, liga, 1):
        assert partido.status is MatchStatus.IN_PROGRESS
        assert partido.match_id in match_registry  # el motor esta corriendo

    for numero_de_fecha in (2, 3):
        for partido in _partidos_de_la_fecha(session, liga, numero_de_fecha):
            assert partido.status is MatchStatus.PENDING
            assert partido.match_id not in match_registry


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
