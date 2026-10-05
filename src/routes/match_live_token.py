"""
Ruta para pedir las credenciales de conexión en vivo a un partido específico.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.core.security import create_ws_global_token, get_current_user
from src.database.base import get_db
from src.schemas.live_token import MatchLiveTokenResponse
from src.services.match_access_service import get_match_in_progress


router = APIRouter(prefix="/api/v1/matches", tags=["matches"])


@router.post("/{match_id}/live-token", response_model=MatchLiveTokenResponse)
def create_match_live_token_endpoint(
    match_id: int,
    user_id: int = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> MatchLiveTokenResponse:
    """
    Devuelve la URL del WebSocket de un partido en curso, con un token de corta duración.

    Se reusa el token del canal global: no lleva el id del partido, así que toda
    la autorización (partido en curso y usuario participante) se revalida en el WS.
    """

    # si el partido no existe o no está en ejecución -> MatchNotFoundError (404)
    match = get_match_in_progress(session, match_id)

    # mismo token que el del canal global - type ws_global
    token = create_ws_global_token(user_id)

    # el token va como query param porque es la única forma de autenticar
    # una conexión WebSocket desde el navegador
    url = f"{settings.WS_BASE_URL}/ws/v1/matches/{match_id}?token={token}"

    return MatchLiveTokenResponse(
        match_id=match_id,
        websocket_url=url,
        expires_in_seconds=settings.WS_GLOBAL_TOKEN_EXPIRE_SECONDS,
    )