"""
Consultas de persistencia sobre Team.
Sólo lectura: la escritura vive en app/services/user_service.py.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from src.models.team import Team

# """ Obtener un usuario con id """ 
# def get_user_by_id(session: Session, user_id: int) -> User | None:
#     return session.get(User, user_id)

""" Obtener el equipo con id """
def get_team_by_id(session: Session, team_id: int) -> Team | None:
    return session.get(Team, team_id)

""" Obtener el equipo por user_id """
def get_team_by_user_id(session: Session, user_id: str) -> Team | None:
    # Obtener el equipo atravez del user_id proporcionado.
    statement = select(Team).where(Team.user_id == user_id)
    return session.scalars(statement).first()