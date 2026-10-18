"""
Generación del fixture de una liga (todos contra todos, una vuelta).
"""

import random
from sqlalchemy.orm import Session
from src.models import League, Match, MatchStatus
from src.repositories.league_repository import get_league_teams


def build_round_robin(team_ids: list[int]) -> list[list[tuple[int, int]]]:
    """
    Devuelve una lista de todas las fechas; cada fecha es una lista de (local_id, visitante_id)
    """
    
    if len(team_ids) % 2 != 0:
        raise ValueError("El fixture solo se puede generar con un numero par de equipos")
    
    # se copia la lista de equipos y se mezcla aleatoriamente para el sorteo
    mixed_teams = team_ids.copy()
    random.shuffle(mixed_teams)

    # Se Agrega la lista de rondas (fechas) que contendrá los pares de equipos
    # con los equipo
    rounds = []
    n = len(mixed_teams)
    for _ in range(n - 1):   # Repite una vez por cada fecha del torneo
        # se crea la lista de pares (en tuplas) de equipos para la fecha actual
        # dentro de la tupla queda definido el local y visitante, (tean_host_id, team_away_id)
        pairs = [(mixed_teams[i], mixed_teams[n - 1 - i]) for i in range(n // 2)]
        # se agrega la lista de pares a la lista de fechas
        rounds.append(pairs)
        # se rota la lista de equipos para la siguiente fecha
        # se rota el primero queda fijo y el último pasa a la posición 1,
        # y al utimo se agega el resto de la lista desde la posición 1 hasta la penúltima
        mixed_teams = [mixed_teams[0]] + [mixed_teams[-1]] + mixed_teams[1:-1]

    # Se invierte el local y visitante en las fechas impares 
    # para que los equipos jueguen de local y visitante de manera equitativa
    for i, round in enumerate(rounds):
        if i % 2 == 1:
            round[0] = (round[0][1], round[0][0])  # invertir local y visitante

    return rounds


def generate_fixture(session: Session, league: League) -> list[Match]:
    """
    Genera todos los partidos de una liga mediante un calendario
    todos contra todos, asignando los equipos locales y visitantes,
    la fecha correspondiente y la duración de cada partido.

    Los partidos se agregan a la sesion y se ejecuta un flush para
    asignar sus IDs, pero no se realiza commit ni se modifica el estado
    de la liga. 
    """

    # se obtiene la lista de equipos inscriptos en la liga y se extraen sus IDs
    teams = get_league_teams(session, league.league_id)
    team_ids = []
    for team in teams:
        team_ids.append(team.team_id)
   
    # se obtiene la lista de fechas con los pares de equipos a enfrentar
    rounds = build_round_robin(team_ids)

    # se crea la lista de partidos a insertar en la base de datos
    matches = []
    # se recorre la lista de fechas y los pares de equipos para crear los partidos
    # enumerate en casa en cada iteración devuelve 2 cosas numero de fecha  y la lista de pares de equipos 
    # y start=1 para que la numeración de fechas comience en 1
    for round_number, current_round in enumerate(rounds, start=1):
        for team_host_id, team_away_id in  current_round:
            match = Match(
                league_id=league.league_id,
                team_host_id=team_host_id,
                team_away_id=team_away_id,
                match_duration=league.match_duration,
                status=MatchStatus.PENDING,
                round_number=round_number
            )
            matches.append(match)

    # se agregan todos los partidos a la sesión y se hace flush para que se asignen los IDs
    # pero no se hace commit, para que todo sea una sola transacción
    session.add_all(matches)
    session.flush() # 

    # retorna la lista de partidos generados, con sus IDs asignados por la base de datos
    return matches
