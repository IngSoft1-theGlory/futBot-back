""" 
Logica de negocio para la entidad League.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.core.exceptions import BadRequestError
from src.models.league import LeagueStatus
from src.repositories.league_repository import get_leagues
from src.schemas.league import LeagueOut

class InvalidQueryParamsError(BadRequestError):
    error_code = "INVALID_QUERY_PARAMS"

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
                teams_current=team_count,
                status=league.status,
                # si tiene password_hash, es privada; si no, es pública. El hash nunca sale del service.
                is_private=league.password_hash is not None,
            )
        )
        
    return result   