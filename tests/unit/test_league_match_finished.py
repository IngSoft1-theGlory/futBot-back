"""
Tests de fin de un partido de liga y avance de fecha
"""

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, call
 
import pytest
from sqlalchemy.orm import sessionmaker
 
from src.models import MatchStatus
from src.realtime.event_bus import event_bus
from src.services import league_run_service
from src.services.league_run_service import _start_round, advance_league, next_round_to_start
from src.services.match_start_service import make_on_finished, save_match_result
from tests.unit.test_start_league_round import _armar_liga_iniciada, _partidos_de_la_fecha
 
 
 
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
 
 
def _estado_final(match_id, goles_local, goles_visitante):
    # on_finished solo lee el id y el marcador, no hace falta un MatchState completo
    return SimpleNamespace(match_id=match_id, score=SimpleNamespace(home=goles_local, away=goles_visitante))
  
 
@pytest.fixture()
def publicar(monkeypatch):
    """Reemplaza event_bus.publish por un mock, para ver que eventos se publicaron."""
    mock = MagicMock() # reemplaza event_bus.publish por un mock, para ver que eventos se publicaron
    monkeypatch.setattr(event_bus, "publish", mock)
    return mock
 
 
@pytest.fixture()
def fabrica_de_sesiones(session):
    """Abre sesiones nuevas sobre la misma base del test, como hace el motor en produccion."""
    return sessionmaker(bind=session.get_bind(), autoflush=False, expire_on_commit=False)
 
 
@pytest.fixture()
def arrancar_fecha(monkeypatch):
    """
    Evita que advance_league arranque partidos de verdad.
    Devuelve el mock de _start_round, que es el que recibe la fecha a arrancar.
    """
    start_round = MagicMock()
    monkeypatch.setattr(league_run_service, "_start_round", start_round)
    monkeypatch.setattr(league_run_service, "_run_in_background", MagicMock())
    return start_round


 
def test_deberia_publicar_los_eventos_de_liga_al_terminar_un_partido(session, publicar):
    liga = _armar_liga_iniciada(session)
    partido = _dejar_un_partido_en_juego(session, liga)
 
    save_match_result(session, partido.match_id, home_goals=2, away_goals=1)
 
    # exactamente estos dos eventos, en este orden
    # el call sirve para comparar que se llamo a la funcion con los argumentos correctos
    assert publicar.call_args_list == [
        call("MATCH_FINISHED", {"match_id": partido.match_id, "status": "FINISHED", "league_id": liga.league_id}),
        call("LEAGUE_MATCH_FINISHED", {
            "league_id": liga.league_id,
            "match_id": partido.match_id,
            "score": {"home": 2, "away": 1},
            "status": "FINISHED",
        }),
    ]
 
 
 
def test_deberia_avisar_a_la_liga_cuando_termina_un_partido_de_liga(session, fabrica_de_sesiones, monkeypatch):
    liga = _armar_liga_iniciada(session)
    partido = _dejar_un_partido_en_juego(session, liga)
    avanzar_liga = MagicMock()
    monkeypatch.setattr(league_run_service, "advance_league", avanzar_liga) # reemplazo advance_league para ver si se llama y con que argumentos
 
    make_on_finished(fabrica_de_sesiones)(_estado_final(partido.match_id, 2, 1))
 
    # ANY es la sesion que abre on_finished, no importa cual sea
    # se llama a advance_league con la liga y la fecha correctas, y con una sesion nueva
    avanzar_liga.assert_called_once_with(ANY, fabrica_de_sesiones, liga.league_id, 1) 
  
 
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
  
 
def test_deberia_arrancar_la_fecha_2_una_sola_vez_cuando_termina_la_fecha_1(
    session, fabrica_de_sesiones, arrancar_fecha
):
    liga = _armar_liga_iniciada(session)
    _terminar_la_fecha(session, liga, 1)
 
    advance_league(session, fabrica_de_sesiones, liga.league_id, 1)
 
    arrancar_fecha.assert_called_once_with(fabrica_de_sesiones, liga.league_id, 2)
 
 
def test_no_deberia_arrancar_ninguna_fecha_si_quedan_partidos_en_curso(session, fabrica_de_sesiones, arrancar_fecha):
    liga = _armar_liga_iniciada(session)
    _dejar_un_partido_en_juego(session, liga)

    # no arranca la fecha 2 porque todavia queda un partido en curso
    advance_league(session, fabrica_de_sesiones, liga.league_id, 1) 
 
    arrancar_fecha.assert_not_called() # no se arranco la fecha 2 porque todavia queda un partido en curso
 
 
@pytest.mark.asyncio
async def test_deberia_arrancar_la_fecha_con_una_sesion_propia(fabrica_de_sesiones, monkeypatch):
    start_league_round = AsyncMock()
    monkeypatch.setattr(league_run_service, "start_league_round", start_league_round)
 
    await _start_round(fabrica_de_sesiones, league_id=7, round_number=2)
 
    start_league_round.assert_awaited_once_with(ANY, 7, 2)
 
 
@pytest.mark.asyncio
async def test_no_deberia_lanzar_error_si_falla_el_arranque_de_la_fecha(fabrica_de_sesiones, monkeypatch):
    start_league_round = AsyncMock(side_effect=Exception("falla"))
    
    # reemplazo start_league_round para que falle, y ver que _start_round no lanza error, solo lo loguea
    monkeypatch.setattr(league_run_service, "start_league_round", start_league_round) 
 
    # solo se loguea, si el error saliera de _start_round, este test fallaria
    await _start_round(fabrica_de_sesiones, league_id=7, round_number=2)
 