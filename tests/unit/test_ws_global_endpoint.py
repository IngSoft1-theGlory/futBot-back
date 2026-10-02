from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.main import app
from src.core.security import create_ws_global_token


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_deberia_aceptar_conexion_con_token_valido(client):
    """Token válido y no vencido -> handshake completo (101)."""
    token = create_ws_global_token(user_id=1)
    with client.websocket_connect(f"/ws/v1/global?token={token}"):
        pass  # si llega aca sin excepción, el handshake se completo


def test_deberia_rechazar_conexion_sin_token(client):
    """Sin token -> rechazado antes del handshake."""
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/v1/global"):
            pass


def test_deberia_rechazar_conexion_con_token_vencido(client):
    """Token vencido -> rechazado antes del handshake."""
    token = create_ws_global_token(user_id=1, expires_delta=timedelta(seconds=-1))
    with pytest.raises(Exception):
        with client.websocket_connect(f"/ws/v1/global?token={token}"):
            pass


def test_deberia_rechazar_conexion_con_token_mal_formado(client):
    """Token corrupto -> rechazado antes del handshake."""
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/v1/global?token=esto.no.es.un.jwt"):
            pass