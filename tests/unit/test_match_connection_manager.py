"""
Tests de MatchConnectionManager. Las "conexiones" son fakes con un
send_json async: no hace falta un WebSocket real ni FastAPI para
probar el registro/desregistro/broadcast.
"""

import pytest

from src.realtime.match_connection_manager import MatchConnectionManager


class _FakeWebSocket:
    def __init__(self, falla: bool = False):
        self.recibidos: list[dict] = []
        self._falla = falla

    async def send_json(self, data: dict) -> None:
        if self._falla:
            raise RuntimeError("conexión cortada")
        self.recibidos.append(data)


@pytest.mark.asyncio
async def test_deberia_broadcast_no_fallar_sin_conectados():
    manager = MatchConnectionManager()
    await manager.broadcast(1, {"event": "TICK_UPDATE"})  # no debe lanzar


@pytest.mark.asyncio
async def test_deberia_entregar_el_mensaje_a_los_conectados_de_ese_partido():
    manager = MatchConnectionManager()
    ws = _FakeWebSocket()
    manager.register(1, ws)

    await manager.broadcast(1, {"event": "TICK_UPDATE", "current_tick": 1})

    assert ws.recibidos == [{"event": "TICK_UPDATE", "current_tick": 1}]


@pytest.mark.asyncio
async def test_deberia_no_entregar_mensajes_de_otro_partido():
    """Dos partidos, cada conexión solo recibe lo suyo."""
    manager = MatchConnectionManager()
    ws_partido_1 = _FakeWebSocket()
    ws_partido_2 = _FakeWebSocket()
    manager.register(1, ws_partido_1)
    manager.register(2, ws_partido_2)

    await manager.broadcast(1, {"current_tick": 1})

    assert ws_partido_1.recibidos == [{"current_tick": 1}]
    assert ws_partido_2.recibidos == []


@pytest.mark.asyncio
async def test_deberia_sacar_del_registro_una_conexion_caida():
    manager = MatchConnectionManager()
    ws_rota = _FakeWebSocket(falla=True)
    manager.register(1, ws_rota)

    await manager.broadcast(1, {"current_tick": 1})  # no debe propagar la excepción

    assert manager.connection_count(1) == 0


@pytest.mark.asyncio
async def test_deberia_una_conexion_caida_no_afectar_a_las_demas():
    manager = MatchConnectionManager()
    ws_rota = _FakeWebSocket(falla=True)
    ws_sana = _FakeWebSocket()
    manager.register(1, ws_rota)
    manager.register(1, ws_sana)

    await manager.broadcast(1, {"current_tick": 1})

    assert ws_sana.recibidos == [{"current_tick": 1}]


@pytest.mark.asyncio
async def test_deberia_broadcast_aguantar_que_alguien_se_conecte_o_desconecte_a_mitad():
    """
    Regresión: send_json cede el control del event loop, y en ese
    momento ws_match.py puede registrar/desregistrar a otro. Si
    broadcast iterara el set original, tiraría RuntimeError ("Set
    changed size during iteration") y mataría al partido.
    """
    import asyncio

    manager = MatchConnectionManager()

    class _WsLento(_FakeWebSocket):
        def __init__(self, al_enviar=None):
            super().__init__()
            self._al_enviar = al_enviar

        async def send_json(self, data: dict) -> None:
            await asyncio.sleep(0)  # cede el control, como una red real
            if self._al_enviar:
                self._al_enviar()
            await super().send_json(data)

    nuevo = _FakeWebSocket()
    primero = _WsLento(al_enviar=lambda: manager.register(1, nuevo))
    manager.register(1, primero)
    manager.register(1, _WsLento())

    await manager.broadcast(1, {"current_tick": 1})  # no debe lanzar

    assert primero.recibidos == [{"current_tick": 1}]
    assert manager.connection_count(1) == 3  # el que entró a mitad quedó registrado


def test_deberia_unregister_sacar_la_conexion():
    manager = MatchConnectionManager()
    ws = _FakeWebSocket()
    manager.register(1, ws)

    manager.unregister(1, ws)

    assert manager.connection_count(1) == 0


def test_deberia_unregister_de_una_conexion_inexistente_no_fallar():
    manager = MatchConnectionManager()
    manager.unregister(999, _FakeWebSocket())  # no debe lanzar
