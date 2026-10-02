from __future__ import annotations

from fastapi import APIRouter, Depends

from src.config.settings import settings
from src.core.security import create_ws_global_token, get_current_user
from src.schemas.live_token import LiveTokenResponse

router = APIRouter(prefix="/api/v1/live-token", tags=["live-token"])


@router.post("/global", response_model=LiveTokenResponse)
def create_live_token_endpoint(user_id: int = Depends(get_current_user)) -> LiveTokenResponse:
    """
    Endpoint para generar un token global de WebSocket.
    Este token es temporal y tiene un tiempo de expiración corto.
    Se utiliza para autenticar la conexión WebSocket en el frontend.
    """
    # get_current_user valida el token HTTP del header Authorization
    # y extrae el user_id del usuario autenticado

    # Genera un token WS de corta duración a partir del user_id
    global_token = create_ws_global_token(user_id) 

    # Arma la URL completa que el cliente va a usar para conectarse al WS.
    # El token va como query param porque es la unica forma de autenticar
    # una conexión WebSocket desde el navegador.
    url = settings.WS_BASE_URL + "/ws/v1/global?token=" + global_token

    return LiveTokenResponse(websocket_url=url, expires_in_seconds=settings.WS_GLOBAL_TOKEN_EXPIRE_SECONDS)

    
