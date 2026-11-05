"""
Tests de cerrar la liga al terminar su ultimo partido
"""

from src.models import LeagueStatus
from src.services.league_run_service import finish_league, next_round_to_start
from tests.unit.test_league_match_finished import _terminar_la_fecha
from tests.unit.test_start_league_round import (  # noqa: F401
    _armar_liga_iniciada,
    cola,
)


def _eventos_publicados(cola):
    """Saca de la cola todos los eventos que se publicaron, en orden."""
    return [cola.get_nowait() for _ in range(cola.qsize())]


def test_deberia_pasar_la_liga_a_finished_y_publicar_el_evento(session, cola):  # noqa: F811
    liga = _armar_liga_iniciada(session)

    finish_league(session, liga.league_id)

    session.refresh(liga)
    assert liga.status == LeagueStatus.FINISHED

    (evento,) = _eventos_publicados(cola)
    assert evento["event"] == "LEAGUE_FINISHED"
    assert evento["data"] == {"league_id": liga.league_id, "status": "FINISHED"}


def test_no_deberia_publicar_el_evento_dos_veces(session, cola):  # noqa: F811
    liga = _armar_liga_iniciada(session)

    finish_league(session, liga.league_id)
    finish_league(session, liga.league_id)  # la segunda vez la liga ya esta terminada

    assert len(_eventos_publicados(cola)) == 1


def test_deberia_cerrar_la_liga_cuando_termina_la_ultima_fecha(session, cola):  # noqa: F811
    liga = _armar_liga_iniciada(session)
    _terminar_la_fecha(session, liga, 3)  # con 4 equipos la ultima fecha es la 3

    # no hay fecha siguiente que arrancar, pero la liga se cierra
    assert next_round_to_start(session, liga.league_id, 3) is None

    session.refresh(liga)
    assert liga.status == LeagueStatus.FINISHED
    assert len(_eventos_publicados(cola)) == 1


def test_no_deberia_cerrar_la_liga_si_todavia_quedan_fechas(session, cola):  # noqa: F811
    liga = _armar_liga_iniciada(session)
    _terminar_la_fecha(session, liga, 1)  # quedan las fechas 2 y 3

    next_round_to_start(session, liga.league_id, 1)

    session.refresh(liga)
    assert liga.status == LeagueStatus.IN_PROGRESS
    assert _eventos_publicados(cola) == []