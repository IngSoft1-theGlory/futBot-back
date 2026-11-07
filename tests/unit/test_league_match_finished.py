"""
Tests del fin de un partido de liga y el avance de fecha
"""

from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, call

import pytest
from sqlalchemy.orm import sessionmaker

from src.core.exceptions import InvalidConfigurationError
from src.models import Match, MatchStatus, Team
from src.realtime.event_bus import event_bus
from src.services import league_run_service
from src.services.league_run_service import advance_league, start_league_match
from src.services.match_start_service import make_on_finished, save_match_result
from tests.unit.test_start_league_round import _armar_liga_iniciada, _partidos_de_la_fecha


def _dejar_un_partido_en_juego(session, liga):
    """En la fecha 1 un partido ya terminó y el otro se está jugando. Devuelve el que se está jugando"""
    terminado, en_juego = _partidos_de_la_fecha(session, liga, 1)
    terminado.status = MatchStatus.FINISHED
    en_juego.status = MatchStatus.IN_PROGRESS
    session.commit()
    return en_juego

def _terminar_la_fecha(session, liga, numero_de_fecha):
    for partido in _partidos_de_la_fecha(session, liga, numero_de_fecha):
        partido.status = MatchStatus.FINISHED
    session.commit()

def _armar_amistoso_en_juego(session):
    """Un partido sin liga (amistoso) con sus dos equipos, ya en juego"""
    local, visitante = Team(team_name="Local"), Team(team_name="Visitante")
    session.add_all([local, visitante])
    session.flush() # flush sirve para que se generen los ids de los equipos antes de crear el partido
    amistoso = Match(
        team_host_id=local.team_id, team_away_id=visitante.team_id,
        match_duration=2, status=MatchStatus.IN_PROGRESS,
    )
    session.add(amistoso)
    session.commit()
    return amistoso

def _estado_final(match_id, goles_local, goles_visitante):
    # on_finished solo lee el id y el marcador, no hace falta un MatchState completo
    return SimpleNamespace(match_id=match_id, score=SimpleNamespace(home=goles_local, away=goles_visitante))

@pytest.fixture()
def publicar(monkeypatch):
    """Reemplaza event_bus.publish por un mock, para ver que eventos se publicaron"""
    mock = MagicMock()
    monkeypatch.setattr(event_bus, "publish", mock)
    return mock

@pytest.fixture()
def fabrica_de_sesiones(session):
    """Abre sesiones nuevas sobre la misma base del test, como hace el motor en produccion"""
    return sessionmaker(bind=session.get_bind(), autoflush=False, expire_on_commit=False)

@pytest.fixture()
def arrancar_fecha(monkeypatch):
    """
    Evita que advance_league arranque partidos de verdad.
    Devuelve el mock de _start_round, que es el que recibe la fecha a arrancar
    """
    start_round = MagicMock()
    monkeypatch.setattr(league_run_service, "_start_round", start_round)
    monkeypatch.setattr(league_run_service, "_run_in_background", MagicMock())
    return start_round


def test_deberia_publicar_los_eventos_de_liga_al_terminar_un_partido(session, publicar):
    liga = _armar_liga_iniciada(session)
    partido = _dejar_un_partido_en_juego(session, liga)

    save_match_result(session, partido.match_id, home_goals=2, away_goals=1)

    # se revisa que estos 2 eventos se publique en este orden
    assert publicar.call_args_list == [
        call("MATCH_FINISHED", {"match_id": partido.match_id, "status": "FINISHED", "league_id": liga.league_id}),
        call("LEAGUE_MATCH_FINISHED", {
            "league_id": liga.league_id,
            "match_id": partido.match_id,
            "score": {"home": 2, "away": 1},
            "status": "FINISHED",
        }),
    ]

def test_deberia_arrancar_la_siguiente_fecha_una_sola_vez_al_finalizar_la_anterior(
    session, fabrica_de_sesiones, arrancar_fecha
):
    liga = _armar_liga_iniciada(session)
    _terminar_la_fecha(session, liga, 1)

    advance_league(session, fabrica_de_sesiones, liga.league_id, 1)
    
    # verifica que se arranca la fecha 2, sino hubiera lanzado un error
    arrancar_fecha.assert_called_once_with(fabrica_de_sesiones, liga.league_id, 2) 

@pytest.mark.asyncio
async def test_deberia_avanzar_la_fecha_si_el_ultimo_partido_se_cierra_0_0_por_no_poder_prepararse(
    session, arrancar_fecha, monkeypatch
):
    liga = _armar_liga_iniciada(session)
    terminado, ultimo_partido = _partidos_de_la_fecha(session, liga, 1)
    terminado.status = MatchStatus.FINISHED
    session.commit()
    # preparar el partido falla, asi que start_league_match lo cierra 0-0
    monkeypatch.setattr(
        league_run_service, "begin_league_match",
        MagicMock(side_effect=InvalidConfigurationError("no se pudo preparar")),
    )

    await start_league_match(session, ultimo_partido.match_id)

    # ANY es la fabrica de sesiones que usa start_league_match, no importa cual sea
    arrancar_fecha.assert_called_once_with(ANY, liga.league_id, 2)

def test_no_deberia_arrancar_ninguna_fecha_nueva_si_termino_la_ultima_fecha(
    session, fabrica_de_sesiones, arrancar_fecha
):
    liga = _armar_liga_iniciada(session)
    _terminar_la_fecha(session, liga, 3)  # con 4 equipos la ultima fecha es la 3

    advance_league(session, fabrica_de_sesiones, liga.league_id, 3)

    arrancar_fecha.assert_not_called() # si la fecha arrarca, es un error porque ya no hay fechas

def test_no_deberia_publicar_eventos_de_liga_ni_avisar_a_la_liga_al_terminar_un_amistoso(
    session, fabrica_de_sesiones, publicar, monkeypatch
):
    amistoso = _armar_amistoso_en_juego(session)
    avanzar_liga = MagicMock()
    # reemplazamos advance_league con un stub para aislar el test y 
    # evitar que se ejecute la implementacion real de avance de liga
    monkeypatch.setattr(league_run_service, "advance_league", avanzar_liga)

    make_on_finished(fabrica_de_sesiones)(_estado_final(amistoso.match_id, 1, 0))

    # solo el MATCH_FINISHED de siempre: sin league_id y sin LEAGUE_MATCH_FINISHED
    assert publicar.call_args_list == [
        call("MATCH_FINISHED", {"match_id": amistoso.match_id, "status": "FINISHED"}),
    ]
    avanzar_liga.assert_not_called()
    