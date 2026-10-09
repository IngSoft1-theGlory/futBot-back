""" 
Servicio para gestionar las ligas.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from sqlalchemy import delete
from src.models.lineup_entry import LineupEntry

from src.schemas.league import CreateLeagueRequest
from src.models.league import League, LeagueStatus
from src.core.security import hash_password
from src.repositories.league_repository import get_league_by_id, is_team_in_league
from src.core.exceptions import (
    InvalidLeagueCapacityError, 
    LeagueNotFoundError, 
    TeamNotInLeagueError,
    HostCannotLeaveError,
    LeagueAlreadyStartedError,
)
from src.services.lineup_service import (
    save_lineup,
    validate_team_belongs_to_user,
    validate_match_duration,
    validate_min_players, 
    validate_lineup,
)

def create_league(session: Session, user_id: int, payload: CreateLeagueRequest) -> League: 
    """
    llama a las validaciones y, si todas pasan, guarda la League 
    y las 6 LineupEntry en una sola transaccion
    """
    validate_team_belongs_to_user(session, user_id, payload.team_id)
    validate_match_duration(payload.match_duration)
    validate_league_capacity(payload.max_teams)
    team_players = validate_min_players(session, payload.team_id)
    validate_lineup(session, payload, team_players)
    
    password_hash = hash_password(payload.password) if payload.password else None 

    try:
        # la liga y los 6 lineup entries se crean aca: si uno falla,
        # tiene que eliminarse todo (rollback) y no quedar nada guardado en la DB.

        # le paso a liga los param necesarios para crear una liga
        league = League(
            league_name = payload.league_name,
            max_teams = payload.max_teams,
            password_hash = password_hash, 
            host_team_id=payload.team_id,
            match_duration=payload.match_duration,
            status=LeagueStatus.PENDING,
        )

        session.add(league)
        session.flush()  # guarda la liga para conseguirle su id, pero todavía se puede deshacer

        # guardo la alineación del anfitrión en la DB 
        save_lineup(session, None, payload.team_id, payload, league.league_id)

        session.commit()  # recién acá queda guardado de verdad (liga y lineup entries)

    except Exception:
        session.rollback()  # deshace todo lo de este intento, liga incluida
        raise

    return league
def validate_league_capacity(max_teams: int) -> None: 
    if max_teams not in (4, 6, 8, 10, 12):
        raise InvalidLeagueCapacityError ("El cupo máximo de la liga debe ser un número par entre 4 y 12")

def exit_league(
        session: Session, 
        user_id: int, 
        league_id: int, 
        team_id: int
) -> None:
    """ 
    Saca al equipo de la liga borrando sus 6 filas de lineup_entries,
    en un orden de las validaciones.
    """
    # Si no existe la liga, lanza LeagueNotFoundError 404
    league = get_league_by_id(session, league_id)
    if league is None:
        raise LeagueNotFoundError("No existe una liga con el ID especificado.")

    # Se valida que el equipo pertenece al usuario, si no, lanza una excepcion
    validate_team_belongs_to_user(session, user_id, team_id)

    # Se valida que el equipo esta inscripto en la liga, 
    # si no lanza TeamNotInLeagueError 404
    if not is_team_in_league(session, league_id, team_id):
        raise TeamNotInLeagueError("El equipo no está inscripto en la liga.")

    # Si el equipo es el anfitrion de la liga, no puede abandonarla
    if league.host_team_id == team_id:
        raise HostCannotLeaveError("El anfitrión no puede abandonar su liga.")

    # Si la liga ya empezó, no se puede abandonar - 409 LEAGUE_ALREADY_STARTED
    if league.status != LeagueStatus.PENDING:
        raise LeagueAlreadyStartedError(
            "La liga ya no está en estado PENDING, no se puede abandonar.")

    # Si sale todo bien, se borran las filas de LineupEntry y se hace commit
    # si hay un error se hace rollback y se lanza la excepcion
    try:
        delete_stmt = delete(LineupEntry).where(
            LineupEntry.league_id == league_id,
            LineupEntry.team_id == team_id
        )
        session.execute(delete_stmt)
        session.commit()
    except Exception:
        session.rollback()
        raise