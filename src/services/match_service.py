"""
Validaciones de negocio del partidos amistosos, mapeadas a los errores del contrato.
"""

from sqlalchemy.orm import Session

from src.models.match import Match, MatchStatus
from src.repositories.match_repository import get_available_matches


def list_friendly_matches(
    session: Session, status: MatchStatus, page: int, limit: int
) -> list[Match]:
    """
    Devuelve una página de amistosos filtrados por estado.
    """
    return get_available_matches(session, status=status, page=page, limit=limit)