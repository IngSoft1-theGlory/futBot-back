"""
Lógica de negocio de POST /api/v1/friendly.
"""

from __future__ import annotations

from typing import NamedTuple

from sqlalchemy.orm import Session

from src.engine.match_runner import ExecuteBehavior
from src.engine._02_to_match.state import MatchState
from src.models import Match, MatchStatus
from src.core.exceptions import InvalidSettingsError, MatchNotFoundError,MatchUnavailableError
from src.repositories.match_repository import claim_pending_match, get_available_matches, get_match_by_id
from src.schemas.friendly import CreateFriendlyRequest, JoinFriendlyRequest
from src.services.lineup_service import save_lineup, validate_team_belongs_to_user, validate_match_duration, validate_min_players, validate_lineup
from src.services.match_start_service import prepare_engine

# Caso de uso 
def create_friendly(session: Session, user_id: int, payload: CreateFriendlyRequest) -> Match:
    """
    llama a las validaciones y, si todas pasan, guarda el Match y las 6 LineupEntry en una sola transacción
    """

    validate_team_belongs_to_user(session, user_id, payload.team_id)
    validate_match_duration(payload.match_duration)
    team_players = validate_min_players(session, payload.team_id)
    validate_lineup(session, payload, team_players, user_id)

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


def get_friendly(session: Session, match_id: int) -> Match:
    """
    Devuelve el amistoso con ese id. Si no existe, lanza MATCH_NOT_FOUND (404).
    """
    match = get_match_by_id(session, match_id)
    if match is None:
        raise MatchNotFoundError("El partido no existe o fue cancelado.")
    return match


class JoinedMatch(NamedTuple):
    """
    resultado de join_friendly: el partido ya confirmado y lo que necesita
    la ruta para lanzar el motor (launch_match) una vez hecho el commit,
    es una NamedTuple para poder desempaquetarla (match, state, execute_behavior = ...)
    y a la vez acceder por nombre (resultado.state).
    """

    match: Match                         # partido ya commiteado, IN_PROGRESS, con el rival
    state: MatchState                    # estado inicial del motor (12 jugadores con PACSS)
    execute_behavior: ExecuteBehavior    # corre el on_tick que cada jugador tiene guardado, en cada tick

def join_friendly(session: Session, user_id: int, match_id: int, payload: JoinFriendlyRequest) -> JoinedMatch:
    """
    Inscribe al equipo rival en un amistoso en espera y lo pasa a IN_PROGRESS.
    Guarda el rival y su alineación en una sola transacción.

    Antes del commit prepara el partido (prepare_match) y asigna a cada jugador el comportamiento de AMBAS alineaciones: 
    si algo de eso falla se hace rollback y el error sale como error de negocio.
    Lanzar el motor (launch_match) es trabajo de la ruta, después del commit.
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
    validate_lineup(session, payload, team_players, user_id)

    try:
        # UPDATE condicional: si otro equipo se unio entre el chequeo de arriba
        # y aca, no actualiza ninguna fila y no se duplica la inscripcion
        if not claim_pending_match(session, match_id, payload.team_id):
            raise MatchUnavailableError("El partido ya comenzó o ya tiene rival.")

        save_lineup(session, match_id, payload.team_id, payload)
        """
         Hasta aca la alineacion del rival es solo un objeto en memoria y el match
         que tengo sigue mostrando "PENDING y sin rival" (el UPDATE de claim_pending_match
         fue directo a la base y no actualizo el objeto). prepare_match lee de la base,
         asi que antes necesito dos cosas:
           flush(): manda las LineupEntry nuevas a la base (esta sesion no tiene
                    autoflush), pero SIN commit: todavia se puede deshacer todo
           refresh(match): recarga el match con el rival y el estado IN_PROGRESS
        """
        session.flush()
        session.refresh(match)
        """
         todo lo que puede fallar del motor se hace ANTES del commit: si falla, el
         except de abajo hace rollback y el partido vuelve a quedar PENDING y sin
         rival (no queda un partido IN_PROGRESS que nadie va a correr)
        """
        state, execute_behavior = prepare_engine(session, match_id)

        session.commit()

    except Exception:
        session.rollback()
        raise

    return JoinedMatch(match, state, execute_behavior)