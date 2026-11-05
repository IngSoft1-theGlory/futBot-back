"""
Tests de fin de un partido de liga y avance de fecha
"""

import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import sessionmaker

from src.models import MatchStatus
from src.services import league_run_service
from src.services.league_run_service import make_league_match_hook, next_round_to_start
from src.services.match_start_service import make_on_finished, save_match_result
from tests.unit.test_start_league_round import (  # noqa: F401
    _armar_liga_iniciada,
    _partidos_de_la_fecha,
    cola,
    frenar_motores,
)


def _dejar_un_partido_en_juego(session, liga):
    """En la fecha 1 un partido ya terminó y el otro se está jugando. Devuelve el que se está jugando."""
    terminado, en_juego = _partidos_de_la_fecha(session, liga, 1)
    terminado.status = MatchStatus.FINISHED
    en_juego.status = MatchStatus.IN_PROGRESS
    session.commit()
    return en_juego


def _terminar_la_fecha(session, liga, numero_de_fecha):
    for partido in _partidos_de_la_fecha(session, liga, numero_de_fecha):
        partido.status = MatchStatus.FINISHED
    session.commit()


def _estados_de_la_fecha(session, liga, numero_de_fecha):
    """Los estados que tienen los partidos de la fecha, sin repetir."""
    return {partido.status for partido in _partidos_de_la_fecha(session, liga, numero_de_fecha)}


def _eventos_publicados(cola):
    """Saca de la cola todos los eventos que se publicaron, en orden."""
    return [cola.get_nowait() for _ in range(cola.qsize())]


async def _esperar_a_que_arranque_la_fecha():
    # el hook no arranca la fecha el mismo: deja una tarea pendiente en el event loop.
    # Acá se espera a que esa tarea termine, para poder revisar el resultado.
    await asyncio.gather(*list(league_run_service._round_start_tasks))


def _fabrica_de_sesiones(session):
    # sesiones nuevas sobre la misma base del test, como las abre el motor en produccion
    return sessionmaker(bind=session.get_bind(), autoflush=False, expire_on_commit=False)


def _estado_final(match_id, goles_local, goles_visitante):
    # on_finished solo lee el id y el marcador, no hace falta un MatchState completo
    return SimpleNamespace(match_id=match_id, score=SimpleNamespace(home=goles_local, away=goles_visitante))


def test_deberia_publicar_los_eventos_de_liga_al_terminar_un_partido(session, cola):  # noqa: F811
    liga = _armar_liga_iniciada(session)
    partido = _dejar_un_partido_en_juego(session, liga)

    save_match_result(session, partido.match_id, home_goals=2, away_goals=1)

    # tienen que ser exactamente dos eventos, en este orden
    match_finished, league_match_finished = _eventos_publicados(cola)
    assert match_finished["event"] == "MATCH_FINISHED"
    assert match_finished["data"]["league_id"] == liga.league_id
    assert league_match_finished["event"] == "LEAGUE_MATCH_FINISHED"
    assert league_match_finished["data"]["score"] == {"home": 2, "away": 1}


def test_deberia_avisar_a_la_liga_con_su_id_y_la_fecha_cuando_termina_un_partido_de_liga(session):
    liga = _armar_liga_iniciada(session)
    partido = _dejar_un_partido_en_juego(session, liga)
    llamadas = []
    on_finished = make_on_finished(
        _fabrica_de_sesiones(session),
        after_league_match=lambda liga_id, fecha: llamadas.append((liga_id, fecha)),
    )

    on_finished(_estado_final(partido.match_id, 2, 1))

    assert llamadas == [(liga.league_id, 1)]


def test_deberia_devolver_la_fecha_siguiente_cuando_terminan_todos_los_partidos_de_la_fecha(session):
    liga = _armar_liga_iniciada(session)
    _terminar_la_fecha(session, liga, 1)

    assert next_round_to_start(session, liga.league_id, 1) == 2


def test_no_deberia_devolver_fecha_si_quedan_partidos_en_curso(session):
    liga = _armar_liga_iniciada(session)
    _dejar_un_partido_en_juego(session, liga)

    assert next_round_to_start(session, liga.league_id, 1) is None


def test_no_deberia_devolver_fecha_si_termino_la_ultima_fecha(session):
    liga = _armar_liga_iniciada(session)
    _terminar_la_fecha(session, liga, 3)  # con 4 equipos hay 3 fechas

    assert next_round_to_start(session, liga.league_id, 3) is None


@pytest.mark.asyncio
async def test_deberia_arrancar_la_fecha_2_cuando_termina_el_ultimo_partido_de_la_fecha_1(
    session, frenar_motores  # noqa: F811
):
    liga = _armar_liga_iniciada(session)
    ultimo_partido = _dejar_un_partido_en_juego(session, liga)
    hook = make_league_match_hook(_fabrica_de_sesiones(session))

    # termina el ultimo partido de la fecha 1 y se avisa a la liga
    save_match_result(session, ultimo_partido.match_id, home_goals=1, away_goals=0)
    hook(liga.league_id, 1)
    await _esperar_a_que_arranque_la_fecha()

    assert _estados_de_la_fecha(session, liga, 2) == {MatchStatus.IN_PROGRESS}
    assert _estados_de_la_fecha(session, liga, 3) == {MatchStatus.PENDING}
    