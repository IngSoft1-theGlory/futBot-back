"""
Servicio para obtener el estado de un partido.
"""

from __future__ import annotations
from dataclasses import dataclass
from sqlalchemy.orm import Session

from src.core.exceptions import (
    ForbiddenError,
    MatchFinishedError,
    MatchNotFoundError,
    MatchPendingError,
    UnauthorizedError,
)
from src.engine._02_to_match.state import MatchRegistry, match_registry
from src.models import MatchStatus, Player
from src.repositories.match_repository import get_match_by_id, get_players_by_team
from src.repositories.user_repository import get_user_by_id
from src.schemas.match_state import (
    MatchPlayerOut,
    MatchStateResponse,
    PlayerAttributesOut,
    ScoreOut,
    PauseOut,
)

import time # para calcular remaining_seconds de la pausa

@dataclass(frozen=True)
class MatchStateContext:
    """ 
    Contexto con la información necesaria para construir la respuesta del estado del partido 
    """
    match_id: int
    user_team_id: int
    players: dict[int, Player]  # player_id -> fila de la DB, de los DOS equipos


def load_match_state_context(session: Session, user_id: int, match_id: int) -> MatchStateContext:
    """ 
    Carga el contexto necesario para construir la respuesta del estado del partido
    """
    
    # se obtiene el partido con get_match_by_id, sino lanza MatchNotFoundError
    match = get_match_by_id(session, match_id)
    if match is None:
        raise MatchNotFoundError("El partido solicitado no existe.")

    # se obtiene el usuario con get_user_by_id, sino lanza UnauthorizedError
    user = get_user_by_id(session, user_id)
    if user is None:
        raise UnauthorizedError("Usuario no encontrado. El token es inválido o el usuario ha sido eliminado.")


    # el equipo del usuario tiene que ser el anfitrión o el visitante sino lanza ForbiddenError 403
    participa = user.team_id == match.team_host_id or (
        match.team_away_id is not None and user.team_id == match.team_away_id
    )
    if not participa:
        raise ForbiddenError("No se permite ver el estado de los partidos en los que no participas.")

    # si el partido está PENDING o FINISHED, lanza MatchPendingError o MatchFinishedError
    if match.status == MatchStatus.PENDING:
        raise MatchPendingError("El partido aún no ha comenzado.")
    if match.status == MatchStatus.FINISHED:
        raise MatchFinishedError("El partido ya ha finalizado.")

    # se obtienen los jugadores de ambos equipos con get_players_by_team
    # obs team_away_id puede ser None entonces hay que verificar 
    # que no sea None antes de llamar a get_players_by_team
    host_players = get_players_by_team(session, match.team_host_id)
    away_players = get_players_by_team(session, match.team_away_id) if match.team_away_id is not None else []

    return MatchStateContext(
        match_id=match.match_id,
        user_team_id=user.team_id,
        players={player.player_id: player for player in host_players + away_players},
    )


    """
    PASO 2 (sin DB y sin await): se arma de corrido, sin cederle el loop al motor.
    Solo LEE el estado en memoria; el filtro de behavior_id se aplica acá, en la
    respuesta, nunca sobre el MatchState.
    """

def build_match_state_response(
    context: MatchStateContext, registry: MatchRegistry = match_registry
) -> MatchStateResponse:

    """ 
    Construye la respuesta del estado del partido a partir del contexto y el registro de partidos. 
    """

    # se obtiene el estado del partido del registro de partidos, sino lanza MatchNotFoundError 404
    state = registry.get(context.match_id)
    if state is None:
        raise MatchNotFoundError("El partido solicitado no existe o no se encuentra en ejecución.")

    # se construye la lista de jugadores con sus atributos y behavior_id, solo si es del equipo del usuario
    players: list[MatchPlayerOut] = []
    for player_id in state.on_pitch_player_ids():
        player_state = state.players[player_id]  
        player = context.players.get(player_id)  
        if player is None:
            raise RuntimeError(
                f"El jugador {player_id} está en el estado del partido {context.match_id} "
                "pero no existe en la base de datos."
            )

        # behavior_id real solo si el jugador es del equipo de quien consulta
        es_propio = player_state.team_id == context.user_team_id
        players.append(
            MatchPlayerOut(
                player_id=player.player_id,
                team_id=player_state.team_id,
                name=player.name,
                number=player.number,
                attributes=PlayerAttributesOut(
                    power=player.power,
                    agility=player.agility,
                    control=player.control,
                    speed=player.speed,
                    strength=player.strength,
                ),
                behavior_id=player_state.behavior_id if es_propio else None,
            )
        )

    # se ordena la lista de jugadores por team_id y luego por player_id
    players.sort(key=lambda p: (p.team_id, p.player_id))

    # Se lee state.pause una sola vez. time.monotonic() 
    # es el mismo reloj con el que se guardó ends_at.
    pause = state.pause
    pause_out = None
    if pause is not None:
        pause_out = PauseOut(
            type=pause.type.value,
            remaining_seconds=max(0.0, pause.ends_at - time.monotonic()),
        )

    return MatchStateResponse(
        match_id=context.match_id,
        current_tick=state.current_tick,
        total_ticks=state.total_ticks,
        score=ScoreOut(home=state.score.home, away=state.score.away),
        players=players,
        phase=state.phase.value,
        pause=pause_out,

    )