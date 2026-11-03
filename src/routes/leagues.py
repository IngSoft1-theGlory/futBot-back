""" 
Rutas relacionadas con ligas.
"""

from __future__ import annotations

from src.schemas.league import VerifyPasswordRequest, VerifyPasswordResponse, CreateLeagueRequest, CreateLeagueResponse
from src.core.security import get_current_user, create_join_token, get_current_user
from src.services.league_service import check_league_password
from fastapi import APIRouter, Depends, status, Response
from src.schemas.league import CreateLeagueRequest, CreateLeagueResponse, LeagueListOut, LeagueDetailOut
from src.services.league_service import create_league, list_leagues, get_league_detail
from src.models import League, LeagueStatus

from fastapi.concurrency import run_in_threadpool

from sqlalchemy.orm import Session

from src.database.base import get_db
from src.realtime.event_bus import event_bus
from src.core.security import get_current_user, create_join_token
from src.services.league_service import (
    create_league, 
    list_leagues, 
    check_league_password, 
    exit_league,
    join_league,
    start_league
)
from src.services.league_run_service import FIRST_ROUND_NUMBER, start_league_round
from src.schemas.league import (
    VerifyPasswordRequest, 
    VerifyPasswordResponse, 
    CreateLeagueRequest, 
    CreateLeagueResponse,
    LeagueListOut,
    JoinLeagueRequest,
    JoinLeagueResponse,
    LeagueDetailOut,
    StartLeagueRequest,
    StartLeagueResponse
)


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
       host_team_id = league.host_team_id,
       penalties_enabled= league.penalties_enabled
    )

@router.delete(
        "/{league_id}/teams/{team_id}", 
        status_code=status.HTTP_204_NO_CONTENT, 
        response_class=Response,
)

async def exit_league_endpoint(
    league_id: int,
    team_id: int,
    user_id: int = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Response:
    """Un equipo no anfitrión abandona la liga antes de que inicie."""
    await run_in_threadpool(exit_league, session, user_id, league_id, team_id)

    # después de hacer commit, aviso a los suscriptores del evento LLEAVE_LOBBY_LEAGUE
    event_bus.publish("LEAVE_LOBBY_LEAGUE", {
        "league_id": league_id,
        "team_id": team_id,
    })

    # responde 204 No Content, op. exitosa pero no hay contenido para devolver
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("", response_model=LeagueListOut, dependencies=[Depends(get_current_user)])
def list_leagues_endpoint(
    page: str | None = None,      
    limit: str | None = None,    
    status: str | None = None,  
    session: Session = Depends(get_db),
):
    # se llama al service para obtener la lista de ligas, con paginación y filtrado por estado
    leagues = list_leagues(session, status=status, page=page, limit=limit)
    return {"leagues": leagues}

@router.post("/{league_id}/verify-password", response_model=VerifyPasswordResponse)
def verify_league_password(
    league_id: int,
    payload: VerifyPasswordRequest,
    user_id: int = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    check_league_password(session, league_id, payload.password)
    return VerifyPasswordResponse(
        join_token=create_join_token(user_id, league_id),
        expires_in_seconds=300,
    )


@router.get("/{league_id}", response_model=LeagueDetailOut)
def get_league_endpoint(
    league_id: int,
    user_id: int = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> LeagueDetailOut:
    """Detalle de una liga: lo usa el lobby (PENDING) y la pantalla de la liga iniciada."""
    return get_league_detail(session, user_id, league_id)

@router.post(
    "/{league_id}/teams",
    response_model=JoinLeagueResponse,
    status_code=status.HTTP_201_CREATED,
)

async def join_league_endpoint(
    league_id: int,
    payload: JoinLeagueRequest,
    user_id: int = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> JoinLeagueResponse:
    """Inscribe un equipo en una liga disponible con su configuración táctica."""
    league = await run_in_threadpool(join_league, session, user_id, league_id, payload)

    # después de hacer commit, aviso a los suscriptores del evento TEAM_JOINED_LEAGUE
    event_bus.publish("TEAM_JOINED_LEAGUE", {
        "league_id": league_id,
        "team_id": payload.team_id,
    })

    # si al unirse se completo el cupo, join_league ya dejo la liga en IN_PROGRESS
    if league.status == LeagueStatus.IN_PROGRESS:
        _publish_league_initiated(league)
        # con la liga confirmada y el evento publicado, arranca la primera fecha
        await start_league_round(session, league_id, FIRST_ROUND_NUMBER)

    return JoinLeagueResponse(league_id=league_id, team_id=payload.team_id)

def _publish_league_initiated(league: League) -> None:
    """ Publica el evento LEAGUE_INITIATED cuando una liga es iniciada. """
    event_bus.publish("LEAGUE_INITIATED", {
        "league_id": league.league_id,
        "league_name": league.league_name,
        "max_teams": league.max_teams,
        "status": league.status.value,
    })

@router.put("/{league_id}", response_model=StartLeagueResponse)
async def start_league_endpoint(
    league_id: int,
    payload: StartLeagueRequest,
    user_id: int = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> StartLeagueResponse:
    """ Inicia con 4 o mas equipos y cantidad par de equipos aunque no este completa"""
    
    # run_in_threadpool corre start_league en otro hilo, porque usa la base de
    # forma bloqueante y trabaría el servidor. El await espera su resultado sin
    # frenar el resto de los pedidos
    league = await run_in_threadpool(start_league, session, user_id, league_id)

    # despues de hacer commit, aviso a los suscriptores del evento LEAGUE_INITIATED
    _publish_league_initiated(league)

    # armo la respuesta antes de arrancar la fecha: asi, si falla algun partido,
    # el PUT igual responde los datos de la liga recien iniciada
    response = StartLeagueResponse(
        league_id=league.league_id,
        league_name=league.league_name,
        status=league.status.value,
    )

    # con la liga confirmada y el evento publicado, arranca la primera fecha
    await start_league_round(session, league_id, FIRST_ROUND_NUMBER)

    # devuelve el estado de la liga recien iniciada
    return response