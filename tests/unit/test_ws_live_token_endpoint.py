from datetime import timedelta
import pytest
from src.core.security import create_ws_global_token, decode_ws_global_token
from src.core.exceptions import UnauthorizedError


def test_token_deberia_ser_aceptado():
    """Un token recién emitido es aceptado."""
    token = create_ws_global_token(user_id=1)
    user_id = decode_ws_global_token(token)
    assert user_id == 1


def test_token_deberia_ser_rechazado_si_expiro():
    """Un token emitido con expiración en el pasado es rechazado."""
    token = create_ws_global_token(user_id=1, expires_delta=timedelta(seconds=-1))
    with pytest.raises(UnauthorizedError):
        decode_ws_global_token(token)


def test_token_deberia_ser_rechazado_si_tipo_incorrecto():
    """Un token HTTP no sirve para el WS."""
    from src.core.security import create_access_token
    token = create_access_token(user_id=1)
    with pytest.raises(UnauthorizedError):
        decode_ws_global_token(token)


def test_token_deberia_ser_rechazado_si_firma_invalida():
    """Un token con firma alterada es rechazado."""
    token = create_ws_global_token(user_id=1)

    # Un JWT tiene la forma header.payload.firma
    # token[:-4] corta los últimos 4 caracteres de la firma,
    # y se reemplazan con "xxxx" para simular una firma corrupta.
    token_alterado = token[:-4] + "xxxx"
    with pytest.raises(UnauthorizedError):
        decode_ws_global_token(token_alterado)