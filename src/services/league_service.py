from __future__ import annotations
from src.schemas.league import CreateLeagueRequest
from src.models.league import League, LeagueStatus
from sqlalchemy.orm import Session
from src.core.exceptions import InvalidLeagueCapacityError, LeagueNotPrivateError, PasswordIncorrectError, LeagueNotFoundError
from src.core.security import hash_password, verify_password
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
        raise LeagueNotFoundError("La liga no fue encontrada")

    if league.password_hash is None: 
        raise LeagueNotPrivateError("La liga que se está intentando verificar no es privada")

    if not(verify_password(password, league.password_hash)):
        raise PasswordIncorrectError("La contraseña ingresada no es correcta")
