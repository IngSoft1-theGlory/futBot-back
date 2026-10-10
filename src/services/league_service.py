from __future__ import annotations
from src.schemas.league import CreateLeagueRequest, JoinLeagueRequest
from src.models.league import League, LeagueStatus
from src.models.lineup_entry import LineupEntry
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from src.core.exceptions import (AlreadyJoinedError,InvalidConfigurationError,InvalidLeagueCapacityError,InvalidLineupError,JoinTokenRequiredError,LeagueFullError,LeagueNotPrivateError,LeagueUnavailableError,NotFoundError,PasswordIncorrectError,)
from src.core.security import hash_password, verify_join_token, verify_password
from src.services.lineup_service import (
    save_lineup,
    validate_team_belongs_to_user,
    validate_match_duration,
    validate_min_players, 
    validate_lineup,
)

def create_league(session: Session, user_id: int, payload: CreateLeagueRequest) -> League: 
    """llama a las validaciones y, si todas pasan, guarda la League y las 6 LineupEntry en una sola transaccion"""

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
     
def check_league_password(session: Session, league_id: int, password: str) -> None:
    league = session.get(League, league_id)

    if league is None: 
        raise LeagueNotPrivateError("La liga no fue encontrada")

    if league.password_hash is None: 
        raise LeagueNotPrivateError("La liga que se está intentando verificar no es privada")

    if not(verify_password(password, league.password_hash)):
        raise PasswordIncorrectError("La contraseña ingresada no es correcta")


def join_league(session: Session, user_id: int, league_id: int, payload: JoinLeagueRequest) -> None:
    """Inscribe al equipo en la liga y guarda su alineación en una sola transacción."""

    validate_team_belongs_to_user(session, user_id, payload.team_id)

    # with_for_update bloquea la fila de la liga para que dos inscripciones simultáneas no superen el cupo
    league = session.scalars(select(League).where(League.league_id == league_id).with_for_update()).first()
    if league is None:
        raise NotFoundError("La liga no existe")
    if league.status != LeagueStatus.PENDING:
        raise LeagueUnavailableError("La liga ya fue iniciada")

    if league.password_hash is not None:
        if payload.join_token is None:
            raise JoinTokenRequiredError("La liga es privada, se requiere un token de unión")
        verify_join_token(payload.join_token, user_id, league_id)

    # un equipo está inscripto si tiene lineup_entries en la liga
    enrolled_team_ids = set(session.scalars(
        select(LineupEntry.team_id).where(LineupEntry.league_id == league_id).distinct()
    ))
    if payload.team_id in enrolled_team_ids:
        raise AlreadyJoinedError("El equipo ya está inscripto en la liga")
    if len(enrolled_team_ids) >= league.max_teams:
        raise LeagueFullError("La liga alcanzó su cupo máximo de equipos")

    team_players = validate_min_players(session, payload.team_id)
    try:
        validate_lineup(session, payload, team_players)
    except InvalidConfigurationError as error:
        raise InvalidLineupError(error.message)

    try:
        save_lineup(session, None, payload.team_id, payload, league_id)
        session.commit()
    except Exception:
        session.rollback()
        raise
