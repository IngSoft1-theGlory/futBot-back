from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from src.core.exceptions import UnauthorizedError
from src.realtime.event_bus import event_bus
from src.core.security import decode_ws_global_token

router = APIRouter(prefix="/ws/v1", tags=["websocket"])


@router.websocket("/global")
async def ws_global_endpoint(websocket: WebSocket, token: str | None = None):

    # se debe validar el token antes de aceptar la conexión, 
    # para evitar que un cliente no autorizado se conecte y se quede colgado en la cola del bus
    if token is None: 
        await websocket.close(code=1008)  # 1008 = Policy Violation
        return

    try: 
        validated_token = decode_ws_global_token(token)
    except UnauthorizedError:
        await websocket.close(code=1008)  # 1008 = Policy Violation
        return
        
    await websocket.accept() # handshake: acepta la conexión WebSocket

    queue = event_bus.subscribe() # registra al nuevo subscriptor y devuelve la cola de eventos de ese subscriptor

    # esperar evento -> enviarlo al cliente (en un loop infinito hasta que el cliente se desconecte)
    try: 
        while True:   
            event = await queue.get()  
            await websocket.send_json(event) 
    except WebSocketDisconnect: 
            pass # desconexion normal del cliente, no es un error
    finally: 
            event_bus.unsubscribe(queue) # al desconectarse, se saca la cola del bus


@router.post("/debug/publish")
def debug_publish():
    from src.realtime.event_bus import event_bus
    event_bus.publish("test_event", {"valor": 42})
    return {"ok": True}

            