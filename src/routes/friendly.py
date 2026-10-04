from __future__ import annotations

from fastapi import APIRouter, Depends, status, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from src.core.security import get_current_user
from src.database.base import get_db
from src.services.friendly_service import create_friendly, list_friendly_matches, join_friendly, get_friendly
from src.models.match import MatchStatus
from src.realtime.event_bus import event_bus
from src.schemas.friendly import (
    CreateFriendlyRequest,
    CreateFriendlyResponse,
    JoinFriendlyRequest,
    JoinFriendlyResponse,
    FriendlyListOut,
    FriendlyLobbyResponse,
)

# Todas las rutas de este archivo empiezan con /api/v1/friendly
router = APIRouter(prefix="/api/v1/friendly", tags=["friendly"])


# POST /api/v1/friendly
# El path va vacío ("") porque el prefix ya tiene la URL completa.
@router.post(
    "",
    response_model=CreateFriendlyResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_friendly_endpoint(
    # FastAPI lee el body del pedido y lo valida contra este schema.
    # Si el formato es incorrecto, responde 422 antes de entrar acá.
    payload: CreateFriendlyRequest,
    # FastAPI extrae el user_id del token de autorización y lo guardo en user_id (o 401)
    user_id = Depends(get_current_user),
    # Sesión de base de datos, abierta para este pedido y cerrada al terminar.
    session: Session = Depends(get_db),
) -> CreateFriendlyResponse:
    """Crea un amistoso."""

    # valido y guardo el partido con create_friendly. Si falla, lanza un error 
    match = create_friendly(session, user_id, payload)

    # armo la respuesta con los datos del partido recien creado y la devuelvo. FastAPI lo convierte a JSON.
    return CreateFriendlyResponse(
        match_id = match.match_id,
        team_host_id = match.team_host_id,
        status = match.status.value,  # create_friendly siempre devuelve PENDING
        match_duration = match.match_duration,
    )

# GET /api/v1/friendly
# El path va vacío ("") porque el prefix ya tiene la URL completa.
@router.get(
    "",
    response_model=FriendlyListOut,
    dependencies=[Depends(get_current_user)],  
)
def list_friendly(
    page: int = Query(1, ge=1),                        # ge=1: page=0 o negativo → 422
    limit: int = Query(20, ge=1, le=100),              # le=100: tope para que nadie pida la tabla entera
    status: MatchStatus = Query(MatchStatus.PENDING),  # valor inválido → 422
    session: Session = Depends(get_db),
):
    matches = list_friendly_matches(session, status=status, page=page, limit=limit)
    return {"matches": matches}

# GET /api/v1/friendly/{match_id}
@router.get(
    "/{match_id}",
    response_model=FriendlyLobbyResponse,
    # solo pide que el usuario esté logueado (o 401); cualquiera puede ver cualquier amistoso
    dependencies=[Depends(get_current_user)],
)
def get_friendly_lobby(
    match_id: int,
    session: Session = Depends(get_db),
) -> FriendlyLobbyResponse:
    ## devuelve el estado del lobby de un amistoso: estado, duracion y los equipos

    # busco el partido, si no existe, lanza 404 MATCH_NOT_FOUND
    match = get_friendly(session, match_id)

    # el rival es None mientras nadie se unio al partido (status PENDING)
    team_away = None
    if match.away_team is not None:
        team_away = match.away_team.to_public_dict()

    return FriendlyLobbyResponse(
        match_id = match.match_id,
        status = match.status.value,
        match_duration = match.match_duration,
        team_host = match.host_team.to_public_dict(),
        team_away = team_away,
    )

# POST /api/v1/friendly/{match_id}/teams
@router.post( ##sto le dice a fastapi que la funcion de abajo va a atender una petición HTTP POST
    "/{match_id}/teams",
    response_model=JoinFriendlyResponse,
    status_code=status.HTTP_200_OK,
)
async def join_friendly_endpoint(
    match_id: int,
    payload: JoinFriendlyRequest, ##este es el body de la peticion HTTP
    user_id = Depends(get_current_user), ##antes de ejecutar esta funcion, ejecuta get_current_user y dame el usuario actual
    session: Session = Depends(get_db),
) -> JoinFriendlyResponse:
    ## une un equipo rival a un amistoso en espera y lo pasa a IN_PROGRESS

    # La ruta es async porque EventBus.publish debe correr en el event loop
    # (sus colas no son thread-safe),el service usa la DB de forma bloqueante,
    # asi que lo mando a un thread para no trabar el loop
    match = await run_in_threadpool(join_friendly, session, user_id, match_id, payload) ##basicamente aca lo que hagp es mandar esta funcion al threadpool y espera su resultado sin bloquear el event loop

    # recien con la union confirmada (commit hecho) se avisa a los suscriptores.
    # Los payloads siguen el catálogo de eventos del contrato de API.
    event_bus.publish("GUEST_JOINED_FRIENDLY", {
        "match_id": match.match_id,
        "team_host_id": match.team_host_id,
        "team_away_id": match.team_away_id,
    })
    event_bus.publish("MATCH_STARTED", {
        "match_id": match.match_id,
        "team_host_id": match.team_host_id,
        "team_away_id": match.team_away_id,
        "status": match.status.value,
    })

    return JoinFriendlyResponse(
        match_id = match.match_id,
        team_host_id = match.team_host_id,
        team_away_id = match.team_away_id,
        status = match.status.value,  # join_friendly siempre devuelve IN_PROGRESS
        match_duration = match.match_duration,
    )
