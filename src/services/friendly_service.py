"""
Lógica de negocio de POST /api/v1/friendly.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.models import Match, MatchStatus
from src.core.exceptions import InvalidSettingsError, MatchNotFoundError, MatchUnavailableError
from src.repositories.match_repository import claim_pending_match, get_match_by_id, get_available_matches
from src.schemas.friendly import CreateFriendlyRequest, JoinFriendlyRequest
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
                
def list_friendly_matches(
    session: Session, status: MatchStatus, page: int, limit: int) -> list[Match]:
    """
    Devuelve una página de amistosos filtrados por estado.
    """
    return get_available_matches(session, status=status, page=page, limit=limit)


def join_friendly(session: Session, user_id: int, match_id: int, payload: JoinFriendlyRequest) -> Match:
    """
    Inscribe al equipo rival en un amistoso en espera y lo pasa a IN_PROGRESS.
    Guarda el rival y su alineación en una sola transacción.
    """

    validate_team_belongs_to_user(session, user_id, payload.team_id)

    match = get_match_by_id(session, match_id)
    if match is None:
        raise MatchNotFoundError("El partido no existe o fue cancelado.")
    if match.status != MatchStatus.PENDING or match.team_away_id is not None:
        raise MatchUnavailableError("El partido ya comenzó o ya tiene rival.")
    # el anfitrion no puede jugar contra sí mismo
    if match.team_host_id == payload.team_id:
        raise InvalidSettingsError("El equipo no puede unirse a su propio partido.")

    team_players = validate_min_players(session, payload.team_id)
    validate_lineup(session, payload, team_players)

    try:
        # UPDATE condicional: si otro equipo se unio entre el chequeo de arriba
        # y aca, no actualiza ninguna fila y no se duplica la inscripcion
        if not claim_pending_match(session, match_id, payload.team_id):
            raise MatchUnavailableError("El partido ya comenzó o ya tiene rival.")

        save_lineup(session, match_id, payload.team_id, payload)

        session.commit()

    except Exception:
        session.rollback()
        raise

    session.refresh(match)  # el UPDATE no pasó por el objeto: lo recargo con el estado nuevo
    return match
