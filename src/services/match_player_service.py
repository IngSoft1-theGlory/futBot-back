"""
Service para cambiar comportamiento durante un partido
"""

from __future__ import annotations

from sqlalchemy.orm import Session
from src.services.match_access_service import get_match_in_progress, user_participates
from src.services.behavior_service import get_behavior
from src.core.exceptions import ForbiddenError, PlayerNotFoundError, InvalidData, MatchNotFoundError
from src.models.behavior import BehaviorType
from src.repositories.user_repository import get_user_by_id
from src.engine._02_to_match.state import match_registry
from src.engine._03_to_builder.behavior_executor import assign_behavior

def validate_behavior_change(session: Session, user_id: int, match_id: int, behavior_id: int) -> tuple[int, str]: 
    # get match in progress tira 404 si el partido no existe o no esta in_progress
    match = get_match_in_progress(session, match_id) 

    if not user_participates(session, user_id, match): 
        raise ForbiddenError("No se permite cambiar comportamientos en partidos en los que no participas")    

    # necesito el user para saber cual es su equipo, asi puedo verificar que intenta modificar el comportamiento de sus propios jugadores
    user = get_user_by_id(session, user_id)
    
    # get behavior tira 404 si el id es invalido (no existe, o no pertenece al usuario y no es default)
    new_behavior = get_behavior(session, user_id=user_id, behavior_id=behavior_id)

    # a un jugador solo se le puede poner un comportamiento de jugador. Si es de DT (COACH) se rechaza acá,
    # antes de apply_behavior_change, así que el jugador conserva el que tenía
    if new_behavior.behavior_type != BehaviorType.PLAYER:
        raise InvalidData("No se pudo cambiar el comportamiento")

    return user.team_id, new_behavior.code


def apply_behavior_change(match_id: int, team_id: int, code : str, player_id: int, behavior_id: int): 
    # busco el estado del partido en el registro 
    registry = match_registry
    
    # me devuelve un Matchstate o None si no esta en curso
    state = registry.get(match_id) 
    if state is None:
        raise MatchNotFoundError("El partido solicitado no existe o no se encuentra en ejecución.")
    
    # si el jugador no existe o no es del equipo del usuario, lanzo 404 
    player = state.players.get(player_id)
    if player is None or player.team_id != team_id:
        raise PlayerNotFoundError("No se ha encontrado el jugador seleccionado") 

    # finalmente le asigno el comportamiento al jugador (no modifico lineup_entries, asi que este cambio es temporal, solo durante el partido en curso)
    try: 
        assign_behavior(player, behavior_id, code)
    except Exception:
        # Atrapo Exception porque assign_behavior
        # ejecuta codigo escrito por usuarios (exec): puede tirar ValueError (sin on_tick), SyntaxError, NameError, etc. 
        raise InvalidData("No se pudo cambiar el comportamiento")