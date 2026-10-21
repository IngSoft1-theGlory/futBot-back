"""
Tests de league_run_service: arrancar un partido de liga.

- begin_league_match: la parte de la base (hasta el commit), sin motor.
- start_league_match: solo se prueba el camino en que el partido no se puede preparar (0-0), que no
  llega a lanzar el motor. Lanzar el motor y publicar MATCH_STARTED se verifica a mano (ver el ticket).

Cada test de error parte de un caso VÁLIDO y cambia UNA sola cosa.
"""

import pytest

from src.core.exceptions import InvalidConfigurationError, MatchUnavailableError
from src.models import Behavior, League, LineupEntry, Match, MatchStatus, Player, Team
from src.realtime.event_bus import event_bus
from src.repositories.match_repository import get_lineup_entries
from src.services.league_run_service import begin_league_match, start_league_match

ROLES_2_1 = ["DEF_LEFT", "DEF_RIGHT", "FORWARD"]
CODIGO_VALIDO = "def on_tick(api): pass"


def _alinear_en_la_liga(session, liga, equipo, comportamiento):
    """Guarda en la liga la alineación de un equipo: 3 titulares y 3 suplentes."""
    # creo los 6 jugadores del equipo
    jugadores = []
    for numero in range(1, 7):
        jugador = Player(
            team_id=equipo.team_id, name=f"Jugador {numero}", number=numero,
            power=1, agility=1, control=1, speed=1, strength=1,
        )
        session.add(jugador)
        jugadores.append(jugador)
    session.flush()  # para que cada jugador tenga su player_id

    # los 3 primeros son titulares, cada uno con su rol
    for i in range(3):
        session.add(LineupEntry(
            league_id=liga.league_id,
            team_id=equipo.team_id,
            player_id=jugadores[i].player_id,
            behavior_id=comportamiento.behavior_id,
            role=ROLES_2_1[i],
            is_starter=True,
        ))

    # los 3 últimos son suplentes, sin rol
    for i in range(3, 6):
        session.add(LineupEntry(
            league_id=liga.league_id,
            team_id=equipo.team_id,
            player_id=jugadores[i].player_id,
            behavior_id=comportamiento.behavior_id,
            role=None,
            is_starter=False,
        ))


def _armar_liga_con_partido(session, codigo=CODIGO_VALIDO):
    """Liga con dos equipos inscriptos (alineados en la liga) y un partido PENDING entre ellos."""
    local = Team(team_name="Local FC")
    visitante = Team(team_name="Visitante FC")
    comportamiento = Behavior(name="Quieto", description="No hace nada", code=codigo, is_default=True)
    session.add_all([local, visitante, comportamiento])
    session.flush()

    liga = League(league_name="Liga", max_teams=4, match_duration=2, host_team_id=local.team_id)
    session.add(liga)
    session.flush()

    # cada equipo tiene su alineación guardada con league_id (3 titulares y 3 suplentes)
    _alinear_en_la_liga(session, liga, local, comportamiento)
    _alinear_en_la_liga(session, liga, visitante, comportamiento)

    partido = Match(
        league_id=liga.league_id, round_number=1, match_duration=2, status=MatchStatus.PENDING,
        team_host_id=local.team_id, team_away_id=visitante.team_id,
    )
    session.add(partido)
    session.commit()
    return partido


def test_deberia_pasar_el_partido_a_in_progress_y_copiar_la_alineacion_de_la_liga(session):
    partido = _armar_liga_con_partido(session)

    begin_league_match(session, partido.match_id)

    # el partido quedo IN_PROGRESS en la base
    session.refresh(partido)
    assert partido.status is MatchStatus.IN_PROGRESS

    # copio las 12 filas al partido, sin league_id
    copiadas = get_lineup_entries(session, match_id=partido.match_id)
    assert len(copiadas) == 12
    assert sum(e.is_starter for e in copiadas) == 6
    assert all(e.league_id is None for e in copiadas)

    # chequeo que las filas de la liga siguen intactas
    assert len(get_lineup_entries(session, league_id=partido.league_id)) == 12


def test_deberia_arrancar_con_la_alineacion_vigente_aunque_la_liga_cambie_despues(session):
    partido = _armar_liga_con_partido(session)
    begin_league_match(session, partido.match_id)

    # despues de arrancar, el usuario cambia el comportamiento de toda la alineación de la liga
    otro = Behavior(name="Otro", description="Tampoco hace nada", code=CODIGO_VALIDO, is_default=True)
    session.add(otro)
    session.commit()
    for entrada in get_lineup_entries(session, league_id=partido.league_id):
        entrada.behavior_id = otro.behavior_id
    session.commit()

    # el partido conserva la alineación con la que arranco (ninguna fila usa el comportamiento nuevo)
    copiadas = get_lineup_entries(session, match_id=partido.match_id)
    assert len(copiadas) == 12
    assert all(e.behavior_id != otro.behavior_id for e in copiadas)


def test_deberia_dejar_el_partido_pending_y_sin_alineacion_si_no_se_puede_preparar(session):
    # un comportamiento sin on_tick: prepare_engine falla antes del commit
    partido = _armar_liga_con_partido(session, codigo="x = 1")

    with pytest.raises(InvalidConfigurationError):
        begin_league_match(session, partido.match_id)

    # rollback completo: sigue PENDING y no quedó ninguna fila copiada
    session.refresh(partido)
    assert partido.status is MatchStatus.PENDING
    assert len(get_lineup_entries(session, match_id=partido.match_id)) == 0


def test_deberia_rechazar_arrancar_un_partido_que_ya_arranco(session):
    partido = _armar_liga_con_partido(session)
    begin_league_match(session, partido.match_id)

    with pytest.raises(MatchUnavailableError):
        begin_league_match(session, partido.match_id)

    # el segundo intento no duplicó la alineación
    assert len(get_lineup_entries(session, match_id=partido.match_id)) == 12


@pytest.mark.asyncio
async def test_deberia_cerrar_el_partido_0_0_y_no_publicar_match_started_si_no_se_puede_preparar(session):
    # un comportamiento sin on_tick: el partido no se puede preparar
    partido = _armar_liga_con_partido(session, codigo="x = 1")
    cola = event_bus.subscribe()

    await start_league_match(session, partido.match_id)

    # el partido se cerró 0-0 en la base
    session.refresh(partido)
    assert partido.status is MatchStatus.FINISHED
    assert (partido.home_goals, partido.away_goals) == (0, 0)

    # y entre los eventos publicados no está MATCH_STARTED
    eventos = [cola.get_nowait()["event"] for _ in range(cola.qsize())]
    event_bus.unsubscribe(cola)
    assert "MATCH_STARTED" not in eventos