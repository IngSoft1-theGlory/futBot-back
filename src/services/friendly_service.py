"""
Lógica de negocio de POST /api/v1/friendly.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.models import Match, MatchStatus
from src.schemas.friendly import CreateFriendlyRequest
from src.services.lineup_service import (
    save_lineup,
    validate_team_belongs_to_user,
    validate_match_duration,
    validate_min_players, 
    validate_lineup,
)

# Caso de uso 
def create_friendly(session: Session, user_id: int, payload: CreateFriendlyRequest) -> Match:
    """
    llama a las validaciones y, si todas pasan, guarda el Match y las 6 LineupEntry en una sola transacción
    """

    validate_team_belongs_to_user(session, user_id, payload.team_id)
    validate_match_duration(payload.match_duration)
    team_players = validate_min_players(session, payload.team_id)
    validate_lineup(session, payload, team_players)

    try:
        # el match y los 6 lineup entries se crean aca: si uno falla,
        # tiene que eliminarse todo (rollback) y no quedar nada guardado en la DB.

        # le paso a Match los param necesarios para crear un amistoso
        # (el id del rival es NULL porque todavía no se unió nadie)
        match = Match(
            team_host_id=payload.team_id,
            match_duration=payload.match_duration,
            status=MatchStatus.PENDING,
        )
        session.add(match)
        session.flush()  # guarda el match para conseguirle su id, pero todavía se puede deshacer

        # guardo la alineación del anfitrión en la DB 
        save_lineup(session, match.match_id, payload.team_id, payload)

        session.commit()  # recién acá queda guardado de verdad (match y lineup entries)

    except Exception:
        session.rollback()  # deshace todo lo de este intento, match incluido
        raise

    return match
                
