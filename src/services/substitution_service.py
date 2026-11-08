"""
Service para hacer una sustitución de jugadores: en una pausa se aplica en el momento;
fuera de ella queda planificada y el motor la aplica cuando empieza la próxima pausa.

Igual que match_player_service, se divide en dos pasos:
  - validate_substitution: consulta la base (lento). La ruta lo corre en un hilo aparte.
  - apply_substitution: trabaja solo con el estado en memoria (rápido y sin await).
"""

from __future__ import annotations

from enum import Enum

from sqlalchemy.orm import Session

from src.core.exceptions import (
    ForbiddenError,
    InvalidPlayerSelectionError,
    ResourceNotFoundError,
    SubstitutionLimitExceededError,
    UnauthorizedError,
)
from src.engine._02_to_match.state import (
    InvalidSubstitutionError,
    SubstitutionLimitError,
    match_registry,
    substitute_player,
    validate_substitution_players,
)
from src.repositories.user_repository import get_user_by_id


def validate_substitution(session: Session, user_id: int, team_id: int) -> None:
    """ Paso 1 (con la base): el usuario del token existe y el team_id de la URL es el de su equipo. """

    user = get_user_by_id(session, user_id)

    # token vigente de un usuario borrado -> 401
    if user is None:
        raise UnauthorizedError("Usuario no encontrado. El token es inválido o el usuario ha sido eliminado.")

    # solo se pueden hacer cambios en el propio equipo -> 403
    if user.team_id != team_id:
        raise ForbiddenError("No está permitido realizar cambios en este equipo")

class SubstitutionResult(Enum):
    APPLIED = "applied"   # había pausa: el cambio se hizo en el momento (201)
    PLANNED = "planned"   # no había pausa: quedó planificado (202)

def apply_substitution(
        match_id: int, 
        team_id: int, 
        player_in_id: int, 
        player_out_id: int,
) -> SubstitutionResult:
    """
    Paso 2 (sin base): aplica el cambio si hay pausa, o lo deja planificado si no la hay.
    Devuelve APPLIED si se aplicó en el momento (201) o PLANNED si quedó planificado (202)
    No puede tener ningún await: se arma de corrido.
    """

    # el partido tiene que estar en ejecución: solo los partidos en curso están en el registry
    state = match_registry.get(match_id)
    if state is None:
        raise ResourceNotFoundError("El partido solicitado no existe o no se encuentra en ejecución.")

    # el equipo tiene que jugar este partido (players_of devuelve [] si no tiene jugadores en él)
    if not state.players_of(team_id):
        raise ForbiddenError("No está permitido realizar cambios en este equipo")

    # los dos jugadores tienen que estar en el partido
    if player_in_id not in state.players or player_out_id not in state.players:
        raise ResourceNotFoundError("No se ha encontrado el jugador seleccionado")

    # Los errores del motor no son AppError (el motor no sabe de HTTP): se traducen acá.
    # NotInPauseError no se traduce porque no puede ocurrir: solo llamamos a substitute_player si hay pausa.
    try:
        if state.pause is not None:
            # hay pausa: el cambio se aplica ya (el motor usa el orden saliente, entrante)
            substitute_player(state, team_id, player_out_id, player_in_id)
            return SubstitutionResult.APPLIED

        # no hay pausa: se valida igual que un cambio real, pero sin tocar a los jugadores
        validate_substitution_players(state, team_id, player_out_id, player_in_id)
        # se guarda el plan; si el equipo ya tenía uno, se pisa. El motor lo aplica al empezar la pausa.
        state.planned_substitutions[team_id] = (player_out_id, player_in_id)
        return SubstitutionResult.PLANNED

    except InvalidSubstitutionError:
        raise InvalidPlayerSelectionError(
            "El jugador seleccionado no está en cancha o el jugador seleccionado no está en el banco de suplentes"
        )
    except SubstitutionLimitError:
        raise SubstitutionLimitExceededError("El equipo ya realizó su cambio en esta pausa")
