from __future__ import annotations

from sqlalchemy.orm import Session

from src.core.exceptions import MatchNotFoundError, UnauthorizedError
from src.models import Match, MatchStatus
from src.repositories.user_repository import get_user_by_id


def get_match_in_progress(session: Session, match_id: int) -> Match:
    """ Devuelve el partido en progreso si existe y está en ejecución, de lo contrario lanza una excepción. """

    # buscar el partido por id (session.get)
    match = session.get(Match, match_id)

    # si no existe O su status no es IN_PROGRESS -> MatchNotFoundError
    if not match or match.status != MatchStatus.IN_PROGRESS:
        raise MatchNotFoundError("El partido solicitado no existe o no se encuentra en ejecución.")

    return match


def user_participates(session: Session, user_id: int, match: Match) -> bool:
    """ Devuelve True si el usuario participa en el partido (es anfitrión o visitante), False si no. """
    
    # buscar el usuario con get_user_by_id
    user = get_user_by_id(session, user_id)

    # si no existe -> UnauthorizedError (token vigente de un usuario borrado)
    if  not user:
        raise UnauthorizedError("Usuario no encontrado. El token es inválido o el usuario ha sido eliminado.")

    # si el usuario tiene un equipo y ese equipo es el anfitrión o el visitante del partido, devuelve True
    # obs: team_away_id puede ser None entonces hay que verificar que no sea None antes de comparar
    return user.team_id == match.team_host_id or (
        match.team_away_id is not None and user.team_id == match.team_away_id)