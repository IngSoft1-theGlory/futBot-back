"""
Consultas de persistencia sobre Team.
Sólo lectura: la escritura vive en app/services/user_service.py.
"""

from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.orm import Session
from src.models.team import Team


def get_team_by_id(session: Session, team_id: int) -> Team | None:
    """ Obtener el equipo con id """
    return session.get(Team, team_id)

def get_teams_count(session: Session) -> int:
    """ Cantidad total de equipos (para total_items y total_pages del ranking global) """
    
    # es un SELECT COUNT(teams.team_id) FROM teams. scalars devuelve el valor
    return session.scalar(select(func.count(Team.team_id)))   

def get_global_ranking_page(session: Session, offset: int, limit: int) -> list[Team]:
    """ Una página del ranking global: puntos, después diferencia de goles, después team_id """
    # calculo diferencia de goles
    goal_diff = Team.goals_for - Team.goals_against

    statement = (
        select(Team)
        .order_by(Team.points.desc(), goal_diff.desc(), Team.team_id)
        .offset(offset)  # cuantos equipos se saltea (las paginas anteriores)
        .limit(limit)    # cuantos equipos devuelve esta pagina
    )

    # scalars devuelve un objeto Team por cada fila y all() los junta en una lista
    return session.scalars(statement).all()