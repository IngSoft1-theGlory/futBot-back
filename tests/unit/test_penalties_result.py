"""
Tests de los penales en el resultado del partido, el fixture de la liga y la tabla de posiciones.
"""

from src.models import Match, MatchStatus
from src.routes.match_result import get_match_result_endpoint
from src.services.league_service import get_league_detail
from src.services.standings_service import build_standings

# reutilizo fixtures y helpers de los tests de la liga y de la tabla
from tests.unit.test_get_league_endpoint import _crear_liga, otro_usuario 
from tests.unit.test_standings_service import _equipos 

def _partido_de_liga_terminado(session, usuario, otro, home_goals=0, away_goals=0,
    home_penalty_goals=None, away_penalty_goals=None):
    """
    Partido de liga terminado entre los dos usuarios.
    """
    liga = _crear_liga(session, usuario.team)
    match = Match(
        team_host_id=usuario.team_id, team_away_id=otro.team_id,
        status=MatchStatus.FINISHED, league_id=liga.league_id,
        match_duration=5, round_number=1, home_goals=home_goals, away_goals=away_goals,
        home_penalty_goals=home_penalty_goals, away_penalty_goals=away_penalty_goals,
    )
    session.add(match)
    session.commit()
    return match

# Resultado del partido ------------------------------------------------------

def test_deberia_devolver_los_goles_de_penales_de_cada_equipo_en_el_resultado(
    session, usuario_con_equipo, otro_usuario
):
    match = _partido_de_liga_terminado(
        session, usuario_con_equipo, otro_usuario,
        home_goals=1, away_goals=1, home_penalty_goals=3, away_penalty_goals=2,
    )

    resultado = get_match_result_endpoint(match.match_id, session)

    assert resultado.home_team.penalty_goals == 3
    assert resultado.away_team.penalty_goals == 2


def test_deberia_devolver_penalty_goals_en_null_si_no_hubo_penales(
    session, usuario_con_equipo, otro_usuario
):
    match = _partido_de_liga_terminado(session, usuario_con_equipo, otro_usuario, home_goals=3, away_goals=1)

    resultado = get_match_result_endpoint(match.match_id, session)

    assert resultado.home_team.penalty_goals is None
    assert resultado.away_team.penalty_goals is None


# Fixture de la liga ---------------------------------------------------------

def test_deberia_devolver_phome_y_paway_en_el_fixture_si_hubo_penales(
    session, usuario_con_equipo, otro_usuario
):
    liga = _partido_de_liga_terminado(
        session, usuario_con_equipo, otro_usuario,
        home_goals=1, away_goals=1, home_penalty_goals=3, away_penalty_goals=2,
    )

    detalle = get_league_detail(session, usuario_con_equipo.user_id, liga.league_id)

    assert detalle.fixture[0].score.phome == 3
    assert detalle.fixture[0].score.paway == 2


def test_deberia_devolver_phome_y_paway_en_null_en_el_fixture_si_no_hubo_penales(
    session, usuario_con_equipo, otro_usuario
):
    liga = _partido_de_liga_terminado(
        session, usuario_con_equipo, otro_usuario, home_goals=2, away_goals=1,
    )

    detalle = get_league_detail(session, usuario_con_equipo.user_id, liga.league_id)

    assert detalle.fixture[0].score.phome is None
    assert detalle.fixture[0].score.paway is None


# Tabla de posiciones --------------------------------------------------------

def test_deberia_dar_2_puntos_al_que_gana_por_penales_y_0_al_que_pierde_sin_modificar_los_goles():
    partido = Match(
        team_host_id=1, team_away_id=2,
        home_goals=1, away_goals=1,
        home_penalty_goals=3, away_penalty_goals=2,
        status=MatchStatus.FINISHED,
    )

    ganador, perdedor = build_standings(_equipos(1, 2), [partido])

    assert (ganador.points, perdedor.points) == (2, 0)
    assert (ganador.goals_for, ganador.goals_against) == (1, 1)