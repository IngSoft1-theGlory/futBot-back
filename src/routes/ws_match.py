from __future__ import annotations

from fastapi import APIRouter, Depends, WebSocket
from sqlalchemy.orm import Session

from src.core.exceptions import AppError
from src.core.security import decode_ws_global_token
from src.database.base import get_db
from src.services.match_access_service import get_match_in_progress, user_participates
from src.realtime.match_connection_manager import match_connections

router = APIRouter(prefix="/ws/v1", tags=["websocket"])


def _puede_conectarse(session: Session, token: str | None, match_id: int) -> bool:
    """
    True si el token es válido y el usuario participa AHORA en este partido en curso.

    El token es el del canal global y no dice nada del partido, así que
    esta función es la única barrera: revalida todo contra la DB.
    """
    try:
        # sin token no se puede conectar
        if not token:
            return False

        # token inválido, vencido o de otro tipo -> UnauthorizedError
        user_id = decode_ws_global_token(token)

        # el partido debe existir y estar en curso -> si no, MatchNotFoundError
        match = get_match_in_progress(session, match_id)

        # el usuario debe jugar este partido (UnauthorizedError si fue borrado)
        return user_participates(session, user_id, match)

    except AppError:
        # en un WebSocket no hay handler global: cualquier error de dominio
        # se traduce en rechazar la conexión
        return False
    finally:
        # la sesión se cierra antes del accept y del loop (pool de la DB)
        session.close()


@router.websocket("/matches/{match_id}")
async def ws_match_endpoint(
    websocket: WebSocket,
    match_id: int,
    token: str | None = None,
    session: Session = Depends(get_db),
):
    """
    Conexión WebSocket de un partido en curso (solo infraestructura de conexión
    y autenticación: los TICK_UPDATE los publica el motor de simulación).
    """

    # si no puede conectarse -> rechazar la conexión con código 1008 (Policy Violation)
    if not _puede_conectarse(session, token, match_id):
        # 1008 = Policy Violation,  el cliente no tiene permiso para conectarse a este partido
        await websocket.close(code=1008)  
        return

    # handshake aceptado, el cliente puede recibir TICK_UPDATE de este partido
    await websocket.accept()
    # registrar la conexión para que el motor de simulación pueda enviarle TICK_UPDATE
    match_connections.register(match_id, websocket)
    
    try:
        # loop infinito hasta que el cliente se desconecte  o cierre el Ws 
        while True:
            # recibir cualquier mensaje del cliente, aunque no se use
            message = await websocket.receive()
            # si el cliente se desconecta, se rompe el loop y se sale del endpoint
            if message["type"] == "websocket.disconnect":
                break
    finally:
        # si el cliente se desconecta, se rompe el loop y se sale del endpoint
        match_connections.unregister(match_id, websocket)