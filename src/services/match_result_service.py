"""
Lógica de negocio del resultado final de un partido
(GET /api/v1/matches/{match_id}/result).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.core.exceptions import MatchNotFinishedError, MatchNotFoundError
from src.models import Match, MatchStatus
from src.repositories.match_repository import get_match_by_id


def get_match_result(session: Session, match_id: int) -> Match:
    """
    Devuelve el partido con ese id solo si ya terminó (su resultado final está
    persistido en home_goals / away_goals).

    - Si no existe: lanza MATCH_NOT_FOUND (404).
    - Si existe pero no está FINISHED (PENDING o IN_PROGRESS): lanza
      MATCH_NOT_FINISHED (400). Los goles de un partido en curso no son el
      resultado final, por eso no se devuelven.
    """
    match = get_match_by_id(session, match_id)
    if match is None:
        raise MatchNotFoundError("El partido solicitado no existe.")
    if match.status != MatchStatus.FINISHED:
        raise MatchNotFinishedError("El resultado final aún no está disponible.")
    return match
