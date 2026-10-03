"""
Conexiones WebSocket activas por partido, para que el motor de
simulación pueda transmitir TICK_UPDATE a quienes estén viendo ESE
partido en particular.

NO reemplaza a EventBus (src/realtime/event_bus.py): ese es el canal
GLOBAL (lobby, un solo flujo para todos los suscriptos). Acá hace
falta algo distinto porque cada partido tiene su propio público: un
cliente conectado a /ws/v1/matches/5 nunca debe recibir los ticks del
partido 8. Por eso las conexiones se guardan agrupadas por match_id,
no en un solo set global.

Nota de arquitectura para más adelante (no bloquea esto): si el
proceso se reinicia, este registro queda vacío aunque la base diga que
el partido sigue IN_PROGRESS. match_access_service valida contra la
base (otra fuente de verdad), así que un cliente podría recibir un
live-token válido para un partido sin motor corriendo del lado del
WS. No es un problema de hoy (un solo proceso, sin reinicios en medio
de un partido), pero va a haber que resolverlo cuando haya más de una
instancia del backend.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Protocol


class _SendsJSON(Protocol):
    """Lo mínimo que necesitamos de una conexión para poder transmitirle
    algo. Protocol (duck typing): en producción es un fastapi.WebSocket,
    en los tests puede ser cualquier objeto con este método async."""

    async def send_json(self, data: dict) -> None: ...


class MatchConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[int, set[_SendsJSON]] = defaultdict(set)

    def register(self, match_id: int, websocket: _SendsJSON) -> None:
        self._connections[match_id].add(websocket)

    def unregister(self, match_id: int, websocket: _SendsJSON) -> None:
        self._connections[match_id].discard(websocket)
        if not self._connections[match_id]:
            del self._connections[match_id]

    def connection_count(self, match_id: int) -> int:
        return len(self._connections.get(match_id, ()))

    async def broadcast(self, match_id: int, message: dict) -> None:
        """
        Envía `message` a todos los conectados a este partido. Si un
        cliente ya se desconectó "a la mala" (la red se cortó antes de
        que ws_match.py llegue a su finally), send_json puede fallar:
        se lo saca del registro en vez de tirar abajo la transmisión
        para el resto de los conectados a este mismo partido.
        """
        dead: list[_SendsJSON] = []
        # Se itera sobre una COPIA (list(...)): cada send_json cede el
        # control del event loop, y mientras tanto ws_match.py puede
        # registrar o desregistrar a otro espectador de este partido.
        # Iterar el set original en ese momento lanza "Set changed size
        # during iteration", que subiría hasta run_match y tiraría
        # abajo el partido entero.
        for websocket in list(self._connections.get(match_id, ())):
            try:
                await websocket.send_json(message)
            except Exception:
                dead.append(websocket)

        for websocket in dead:
            self.unregister(match_id, websocket)


# Instancia única: ws_match.py registra/desregistra acá, y el motor
# (vía match_broadcast.notify) transmite por acá. Mismo patrón que
# event_bus en este mismo paquete.
match_connections = MatchConnectionManager()
