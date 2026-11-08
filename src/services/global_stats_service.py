"""
Estadisticas globales de los clubes (las que usa el ranking global)

Cuando termina un partido de una liga publica, se suma su resultado a los dos equipos

Los amistosos y los partidos de ligas privadas no suman

El resultado de cada equipo y sus puntos se calculan con las mismas reglas que la tabla de posiciones de una liga (standings_service), asi las dos nunca se contradicen
"""

from sqlalchemy.orm import Session

from src.models import Match, Team
from src.repositories.league_repository import get_league_by_id
from src.services.standings_service import DRAW, LOSS, POINTS, get_match_result


def add_match_to_global_stats(session: Session, match: Match) -> bool:
    """
    Suma el resultado del partido a las estadisticas globales de sus dos equipos y devuelve True si sumo (el ranking cambio) o False si el partido no cuenta
    """
    # los amistosos no tienen liga -> no suman
    if match.league_id is None:
        return False

    # una liga es privada si tiene contraseña -> sus partidos tampoco suman
    league = get_league_by_id(session, match.league_id)
    if league.password_hash is not None:
        return False

    # el resultado de cada equipo osea WIN, DRAW, LOSS o PENALTY_WIN (gano por penales)
    home_result, away_result = get_match_result(match)

    # cada equipo suma sus goles a favor y en contra
    _add_result_to_team(match.host_team, match.home_goals, match.away_goals, home_result)
    _add_result_to_team(match.away_team, match.away_goals, match.home_goals, away_result)
    return True


def _add_result_to_team(team: Team, goals_for: int, goals_against: int, result: str) -> None:
    # Suma un partido jugado a las estadisticas de un equipo
    team.matches_played += 1
    team.goals_for += goals_for
    team.goals_against += goals_against
    team.points += POINTS[result]  # 3 por victoria, 1 por empate, 0 por derrota (2 si gano por penales)

    if result == DRAW:
        team.draws += 1
    elif result == LOSS:
        team.losses += 1
    else:  # WIN o PENALTY_WIN: las dos son victorias
        team.wins += 1
