from __future__ import annotations

from fastapi import APIRouter, Depends, status, Response

from fastapi.concurrency import run_in_threadpool

from sqlalchemy.orm import Session

from src.schemas.league import CreateLeagueRequest, CreateLeagueResponse
from src.services.league_service import create_league, exit_league
from src.core.security import get_current_user
from src.realtime.event_bus import event_bus
from src.database.base import get_db

# Todas las rutas de este archivo empiezan con /api/v1/leagues
router = APIRouter(prefix="/api/v1/leagues", tags=["leagues"])


# POST /api/v1/leagues
# El path va vacío ("") porque el prefix ya tiene la URL completa.
@router.post(
    "",
    response_model=CreateLeagueResponse,
    status_code=status.HTTP_201_CREATED,
)

async def create_league_endpoint(
    # FastAPI lee el body del pedido y lo valida contra este schema.
    # Si el formato es incorrecto, responde 422 antes de entrar aca
    payload: CreateLeagueRequest,
    # FastAPI extrae el user_id del token de autorizacion y lo guarda en user_id (o 401)
    user_id = Depends(get_current_user),
    # Sesión de base de datos, abierta para este pedido y cerrada al terminar.
    session: Session = Depends(get_db),
) -> CreateLeagueResponse:
    """Crea una liga."""

    # run_in_threadpool corre create_league en otro hilo, porque usa la base de
    # forma bloqueante y trabaría el servidor. El await espera su resultado sin
    # frenar el resto de los pedidos.
    league = await run_in_threadpool(create_league, session, user_id, payload) # create_league valida, guarda la liga y hace el commit

    is_private = league.password_hash is not None

    # después de hacer commit, aviso a los suscriptores del evento LEAGUE_CREATED
    event_bus.publish("LEAGUE_CREATED", {
        "league_id": league.league_id,
        "league_name": league.league_name, 
        "max_teams": league.max_teams, 
        "status": league.status.value
    })

    # armo la respuesta con los datos del partido recien creado y la devuelvo. FastAPI lo convierte a JSON.
    return CreateLeagueResponse(
       league_id = league.league_id, 
       league_name = league.league_name,
       status = league.status.value, 
       is_private = is_private,
       match_duration = league.match_duration,
       max_teams = league.max_teams, 
       current_teams_count = 1,
       host_team_id = league.host_team_id
    )

# DELETE /api/v1/leagues/{league_id}/teams/{team_id}
# El path tiene dos parametros, league_id y team_id, 
# donde FastAPI extrae de la URL y pasa a la funcion
@router.delete(
    "/{league_id}/teams/{team_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)

def leave_league_endpoint(
    league_id: int,
    team_id: int,
    user_id: int = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Response:
    """Un equipo no anfitrión abandona la liga antes de que inicie."""
    exit_league(session, user_id, league_id, team_id)

    # responde 204 No Content, op. exitosa pero no hay contenido para devolver
    return Response(status_code=status.HTTP_204_NO_CONTENT)