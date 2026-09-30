"""
Consultas de persistencia sobre Amistosos.
Sólo lectura: la escritura vive en app/services/match_service.py.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.match import Match, MatchStatus

"""Devuelve una página de amistosos disponibles"""
def get_available_matches(
    session: Session,
    status: MatchStatus | None = MatchStatus.PENDING, # por defecto solo partidos disponibles
    page: int = 1,                                    # por defecto, la primer pagina
    limit: int = 20,                                  # por defecto, 20 partidos por pagina
) -> list[Match]:

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