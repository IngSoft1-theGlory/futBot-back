"""
Consultas de persistencia sobre partidos
Sólo lectura: la escritura vive en src/services/friendly_service.py.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import Behavior, Player
from src.models.match import Match, MatchStatus


def get_players_by_team(session: Session, team_id: int) -> list[Player]:
    """Todos los jugadores del equipo."""
    statement = select(Player).where(Player.team_id == team_id)

    # scalars devuelve los objetos sueltos, no envueltos en tuplas
    return list(session.scalars(statement).all())

def get_behaviors_by_ids(session: Session, behavior_ids: list[int]) -> list[Behavior]:
    """Los comportamientos que existan entre esos ids (los que falten no vienen)."""
    statement = select(Behavior).where(Behavior.behavior_id.in_(behavior_ids))
    
    return list(session.scalars(statement).all())

def get_available_matches(
    session: Session,
    status: MatchStatus | None = MatchStatus.PENDING, # por defecto solo partidos disponibles
    page: int = 1,                                    # por defecto, la primer pagina
    limit: int = 20,                                  # por defecto, 20 partidos por pagina
) -> list[Match]:
    """Devuelve una página de amistosos disponibles"""
    
    # Consulta de partidos disponibles.
    # El estado va fijo el usuario no puede elegir otro.
    match_query = select(Match).where(Match.status == status)

    match_query = (
        match_query
        # Ordenar partidos en base a su match_id de forma descendente
        .order_by(Match.match_id.desc())
        # Salta los partidos de las páginas anteriores (página 1 salta 0).
        .offset((page - 1) * limit)
        # Trae como máximo los partidos de una pagina
        .limit(limit)
    )

    # Se ejecuta la consulta y la convierte en lista
    # Si no hay filas, devuelve []
    return list(session.scalars(match_query).all())