"""
Consultas de persistencia sobre partidos
Sólo lectura: la escritura vive en src/services/friendly_service.py.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import Behavior, LineupEntry, Match, Player


def get_players_by_team(session: Session, team_id: int) -> list[Player]:
    """Todos los jugadores del equipo."""
    statement = select(Player).where(Player.team_id == team_id)

    # scalars devuelve los objetos sueltos, no envueltos en tuplas
    return list(session.scalars(statement).all())

def get_behaviors_by_ids(session: Session, behavior_ids: list[int]) -> list[Behavior]:
    """Los comportamientos que existan entre esos ids (los que falten no vienen)."""
    statement = select(Behavior).where(Behavior.behavior_id.in_(behavior_ids))
    
    return list(session.scalars(statement).all())

def get_match_by_id(session: Session, match_id: int) -> Match | None:
    """El partido con ese id, o None si no existe."""
    return session.get(Match, match_id)

def get_lineup_entries(session: Session, match_id: int) -> list[LineupEntry]:
    """Las entradas de alineación de AMBOS equipos del partido, en orden de creación."""
    statement = (
        select(LineupEntry)
        .where(LineupEntry.match_id == match_id)
        .order_by(LineupEntry.entry_id)
    )

    return list(session.scalars(statement).all())