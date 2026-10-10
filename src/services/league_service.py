""" 
Logica de negocio para la entidad League.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.schemas.league import CreateLeagueRequest, LeagueOut
from src.models.league import League, LeagueStatus
from src.repositories.league_repository import get_leagues
from src.core.security import hash_password, verify_password
from src.core.exceptions import (
    InvalidLeagueCapacityError, 
    LeagueNotPrivateError, 
    PasswordIncorrectError,
    InvalidQueryParamsError
)
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

<<<<<<< HEAD

def validate_league_capacity(max_teams: int) -> None: 
    if max_teams not in (4, 6, 8, 10, 12):
        raise InvalidLeagueCapacityError ("El cupo máximo de la liga debe ser un número par entre 4 y 12")


def list_leagues(session: Session, page: str | None, limit: str | None, status: str | None) -> list[LeagueOut]:
    """ 
    obtiene un listado de ligas, filtradas por status y paginadas por page y limit.
    Valida los parametros de entrada y lanza InvalidQueryParamsError si alguno es invalido
    """
    # Validacion de page y limit: si no son enteros positivos, 
    # lanza InvalidQueryParamsError
    if page is None:
        page_int = 1
    else:
        try:
            page_int = int(page)
        except ValueError:
            raise InvalidQueryParamsError("page debe ser un entero positivo.") from None
        if page_int < 1:
            raise InvalidQueryParamsError("page debe ser un entero positivo.")

    if limit is None:
        limit_int = 20
    else:
        try:
            limit_int = int(limit)
        except ValueError:
            raise InvalidQueryParamsError("limit debe ser un entero positivo.") from None
        if limit_int < 1:
            raise InvalidQueryParamsError("limit debe ser un entero positivo.")
        if limit_int > 100:
            raise InvalidQueryParamsError("limit no puede ser mayor a 100.")

    # Validacion de status: si no es None, intentar convertirlo a LeagueStatus; 
    # si falla, lanza InvalidQueryParamsError
    if status is None: # Si no se envia un estado, se mantiene None y devuelve todas las ligas
        status_enum = None
    else:
        try:
            status_enum = LeagueStatus(status)
        except ValueError:
            # Se lanza InvalidQueryParamsError con un mensaje que indica los valores válidos de status
            raise InvalidQueryParamsError(
                f"status debe ser uno de {', '.join(s.value for s in LeagueStatus)}."
                ) from None

    # Se obtienen las ligas  de la base de datos filtrados y validados.
    rows = get_leagues(
        session,
        status=status_enum,
        page=page_int,
        limit=limit_int,
    )

    # Se construye la lista de ligas a devolver, con el formato requerido por LeagueOut
    result = []
    for league, team_count in rows:
        result.append(
            LeagueOut(
                league_id=league.league_id,
                league_name=league.league_name,
                max_teams=league.max_teams,
                current_teams_count=team_count,
                status=league.status,
                # si tiene password_hash, es privada; si no, es pública. El hash nunca sale del service.
                is_private=league.password_hash is not None,
            )
        )
        
    return result  
=======
  
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
>>>>>>> origin/develop
