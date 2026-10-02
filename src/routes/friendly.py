from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from src.core.security import get_current_user
from src.database.base import get_db
from src.schemas.friendly import CreateFriendlyRequest, CreateFriendlyResponse
from src.services.friendly_service import create_friendly

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