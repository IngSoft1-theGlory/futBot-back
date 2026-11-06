""" 
Módulo de servicio para la tabla de posiciones
"""
from src.models import Match, Team
from src.schemas.league import StandingRowOut

WIN, DRAW, LOSS, PENALTY_WIN = "WIN", "DRAW", "LOSS", "PENALTY_WIN"
POINTS = {WIN: 3, DRAW: 1, LOSS: 0, PENALTY_WIN: 2}
RESULT_FIELD = {WIN: "wins", DRAW: "draws", LOSS: "losses", PENALTY_WIN: "wins"}  # PENALTY_WIN se cuenta como victoria en la tabla de posiciones


def get_match_result(match):
    """ 
    Calcula el resultado de un partido (victoria, empate, derrota o victoria por penales) para el equipo local y el visitante.
    """
    if match.home_goals > match.away_goals:
        return WIN, LOSS
    if match.home_goals < match.away_goals:
        return LOSS, WIN
    if match.home_penalty_goals is not None and match.away_penalty_goals is not None:
        if match.home_penalty_goals > match.away_penalty_goals:
            return PENALTY_WIN, LOSS
        if match.home_penalty_goals < match.away_penalty_goals:
            return LOSS, PENALTY_WIN
    return DRAW, DRAW


def standings_sort_key(item):
    """ 
    Función para ordenar las posiciones por puntos, 
    diferencia de goles, goles a favor, goles en contra y ID del equipo.
    """
    team_id, stats = item

    return (
        stats["points"],
        stats["goal_diff"],
        stats["goals_for"],
        -stats["goals_against"],
        -team_id,
    )


def build_standings(teams: list[Team], matches: list[Match]) -> list[StandingRowOut]:
    """ 
    Construye la tabla de posiciones de la liga a partir de los equipos y partidos 
    """
    
    # se crea un diccionario con team_id como clave y otro diccionario con los stats como valor
    # cada campo de stats se inicializa en 0, incluso los equipos que no jugaron ningún partido
    team_stats = {team.team_id: {
        "matches": 0,
        "wins": 0,
        "draws": 0,
        "losses": 0,
        "goals_for": 0,
        "goals_against": 0,
        "points": 0
    } for team in teams}
    
    # por cada partido, actualizar las estadísticas de los equipos locales y visitantes,
    # que se obtiene del dicionario team_stats
    # la información de cada partido se obtiene desde el objeto Match, que tiene los atributos 
    # team_host_id, team_away_id, home_goals, away_goals, home_penalty_goals y away_penalty_goals
    for match in matches:
        home_team_id = match.team_host_id
        away_team_id = match.team_away_id
        home_goals = match.home_goals
        away_goals = match.away_goals
        
        # actualizar estadísticas del equipo local
        team_stats[home_team_id]["matches"] += 1
        team_stats[home_team_id]["goals_for"] += home_goals
        team_stats[home_team_id]["goals_against"] += away_goals
        
        # actualizar estadísticas del equipo visitante
        team_stats[away_team_id]["matches"] += 1
        team_stats[away_team_id]["goals_for"] += away_goals
        team_stats[away_team_id]["goals_against"] += home_goals

        # calcular el resultado de cada partido y actualizar las estadísticas
        home_result, away_result = get_match_result(match)
       
        # recorre al equipo local y al visitante con su resultado correspondiente (estadisticas)
        # y actualiza sus victorias, empates, derrotas y puntos.
        for team_id, result in (
            (match.team_host_id, home_result), 
            (match.team_away_id, away_result)
        ):
            team_stats[team_id][RESULT_FIELD[result]] += 1
            team_stats[team_id]["points"] += POINTS[result]
    
    # calcular la diferencia de goles para cada equipo
    # es la resta de goles a favor menos goles en contra
    # items = (team_id, stats) donde stats es un diccionario con las estadísticas
    for team_id, stats in team_stats.items():
        stats["goal_diff"] = stats["goals_for"] - stats["goals_against"]

    # Ordena los equipos según los criterios definidos en standings_sort_key().
    # reverse=True prioriza los valores más altos; los valores negados permiten
    # que menos goles en contra y un menor ID queden primero.
    team_stats = sorted(
        team_stats.items(), # se el par del diccionario (team_id, stats)
        key=standings_sort_key, # el par del dicc se pasa a la func que devuelve una tupla con los criterios de ord
        reverse=True # se ordena descendentemente para que los valores más altos queden primero
    )
    
    # Crear la lista de posiciones finales, donde cada posición es un objeto StandingRowOut
    # Se recorre la lista de equipos ordenados y se asigna la posición correspondiente
    standings = []
    for position, (team_id, stats) in enumerate(team_stats):
        standings.append(StandingRowOut(
            position=position + 1,
            team_id=team_id,
            team_name=next(team.team_name for team in teams if team.team_id == team_id),
            matches_played=stats["matches"],
            wins=stats["wins"],
            draws=stats["draws"],
            losses=stats["losses"],
            goals_for=stats["goals_for"],
            goals_against=stats["goals_against"],
            goal_diff=stats["goal_diff"],
            points=stats["points"]
        ))

    return standings