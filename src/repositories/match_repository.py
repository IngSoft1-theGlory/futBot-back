"""
Consultas de persistencia sobre partidos
Sólo lectura: la escritura vive en src/services/friendly_service.py.
"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.models import Behavior, Match, MatchStatus, Player


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
    """El partido con ese id, o None si no existe"""
    return session.get(Match, match_id)


def claim_pending_match(session: Session, match_id: int, away_team_id: int) -> bool:
    """Anota al rival y pasa el partido a IN_PROGRESS en un solo UPDATE condicional
    solo lo logra quien lo encuentre todavia PENDING y sin rival: si dos equipos
    compiten, la base deja pasar a uno solo,devuelve False si perdió la carrera, osea
    esto tambien maneja la condicion de carrera
    """
    statement = ( ##aca empieza a construir una consulta SQL
        update(Match) ##indica que queremos hacer un update sobre la tabla de match
        .where( ##las condiciones que deben cumplirse para permitir el update
            Match.match_id == match_id,
            Match.status == MatchStatus.PENDING,
            Match.team_away_id.is_(None), ##osea no tiene que tener un equipo visitante 
        )
        .values(team_away_id=away_team_id, status=MatchStatus.IN_PROGRESS)
    )
    result = session.execute(statement)
    return result.rowcount == 1 ##las filas que modifico, si es 0 es porque no cumplio una condicion y es 1 si salio todo bien y se unio al partido
