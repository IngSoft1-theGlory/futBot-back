"""service para elegir el comportamiento del DT"""
from sqlalchemy.orm import Session

from src.schemas.league import ChooseCoachResponse, ChooseCoachRequest
from src.models.behavior import BehaviorType
from src.models.league import LeagueStatus
from src.repositories.league_repository import get_league_by_id, is_team_in_league
from src.services.behavior_service import get_behavior
from src.services.lineup_service import validate_team_belongs_to_user
from src.engine._02_to_match.state import coach_registry

from src.core.exceptions import (
    InvalidData,
    LeagueNotFoundError,
    LeagueNotInProgressError,
    TeamNotInLeagueError,
)

def choose_coach_behavior(session: Session, league_id: int, user_id: int, team_id: int, payload: ChooseCoachRequest) -> ChooseCoachResponse: 
    """
    Elige (o quita, con None) el comportamiento de DT de un equipo en una liga.
    Solo se permite con la liga en curso. Rige desde el próximo partido.
    """
    league = get_league_by_id(session, league_id)
    if league is None:
        raise LeagueNotFoundError("No existe una liga con el ID especificado.") 

    # tira 403 si el equipo no pertenece al usuario
    validate_team_belongs_to_user(session, user_id, team_id)

    if not is_team_in_league(session, league_id, team_id):
        raise TeamNotInLeagueError("El equipo no está inscripto en la liga.") # otro 404

    if league.status != LeagueStatus.IN_PROGRESS:
        raise LeagueNotInProgressError("El director técnico solo se puede elegir mientras la liga está en curso") # solo puedo elegir DT para ligas en curso

    if payload.behavior_id is None:
        coach_registry.remove(league_id, team_id) # si me pasan None, se quita el comportamiento de DT del equipo en la liga
    else:
        behavior = get_behavior(session, user_id=user_id, behavior_id=payload.behavior_id)
        if behavior.behavior_type != BehaviorType.COACH:
            raise InvalidData("El comportamiento no es de director técnico.")
        # si esta todo bien, guardo el comportamiento de DT para el equipo en la liga. se aplica desde el proximo partido
        coach_registry.set(league_id, team_id, payload.behavior_id)

    return ChooseCoachResponse(
        league_id=league_id, team_id=team_id, behavior_id=payload.behavior_id
    )