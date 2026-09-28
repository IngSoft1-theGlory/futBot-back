from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from src.config.settings import settings
from src.core.security import ALGORITHM, create_access_token, get_current_user


@pytest.fixture
def app():
    """
    App mínima con un solo endpoint protegido, para probar
    get_current_user sin depender de los endpoints reales del proyecto.
    """
    app = FastAPI()

    @app.get("/protected")
    def protected(current_user: int = Depends(get_current_user)):
        return {"user_id": current_user}

    return app


@pytest.fixture
def client(app):
    # TestClient simula requests HTTP en memoria, sin levantar ningún
    # servidor real ni abrir ningún puerto.
    return TestClient(app)


def test_crear_token_contiene_user_id():
    """El JWT generado debe contener el user_id (como 'sub')."""
    token = create_access_token(user_id=123)

    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])

    # sub siempre viaja como string, por eso se compara contra "123" y no 123
    assert payload["sub"] == "123"


def test_crear_token_contiene_expiracion():
    """El JWT debe contener una fecha de expiración."""
    token = create_access_token(user_id=123)

    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])

    assert "exp" in payload


def test_crear_token_expiracion_es_futura():
    """
    exp tiene que ser una fecha real y
    posterior a ahora, no cualquier valor.
    """
    token = create_access_token(user_id=123)

    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])

    # pyjwt guarda 'exp' como timestamp numérico, lo convierto a datetime
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

    assert exp > datetime.now(timezone.utc)


def test_token_valido_permite_acceso(client):
    """
    token valido -> 200 OK -> y el user_id
    devuelto es el mismo que genero el token (no cualquier usuario).
    """
    token = create_access_token(user_id=123)

    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["user_id"] == 123


def test_token_ausente_devuelve_401(client):
    """
    Sin header Authorization tiene que dar 401, nunca 403 (default de
    HTTPBearer que esta desactivado a proposito con auto_error=False).
    """
    response = client.get("/protected")

    assert response.status_code == 401


def test_token_invalido_devuelve_401(client):
    """Un string cualquiera, que ni siquiera tiene forma de JWT, da 401."""
    response = client.get(
        "/protected", headers={"Authorization": "Bearer token-invalido"}
    )

    assert response.status_code == 401


def test_token_manipulado_devuelve_401(client):
    """
    Corrompe el payload de un token valido sin volver a firmarlo:
    prueba que la firma protege contra manipulacion, no solo que
    un texto random no parsea.
    """
    token = create_access_token(user_id=123)

    parts = token.split(".")
    tampered_token = parts[0] + "." + parts[1][::-1] + "." + parts[2]

    response = client.get(
        "/protected", headers={"Authorization": f"Bearer {tampered_token}"}
    )

    assert response.status_code == 401


def test_token_expirado_devuelve_401(client):
    """Un token expirado da 401."""
    # se le pasa a create_access_token una duración negativa, asi el test usa el mismo camino real
    # que usaria el login, solo que con el resultado ya vencido.
    token = create_access_token(user_id=123, expires_delta=timedelta(minutes=-1))

    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_token_firmado_con_clave_incorrecta_devuelve_401(client):
    """
    Un token bien formado, pero firmado con una clave distinta a nuestra secret_key, debe ser rechazado.
    """
    payload = {
        "sub": "123",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = jwt.encode(payload, "otra-secret-key-cualquiera", algorithm=ALGORITHM)

    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_token_usa_secret_key_de_settings(monkeypatch):
    """
    create_access_token firma con el SECRET_KEY que tenga cargado
    `settings` en ese momento, nunca con un valor hardcodeado en el
    código — si cambia el de settings, cambia la firma resultante.
    """
    otra_clave = "secret-de-prueba"

    # setattr cambia SECRET_KEY en el objeto settings ya creado, solo
    # para este test. monkeypatch lo devuelve a su valor original al final.
    monkeypatch.setattr(settings, "SECRET_KEY", otra_clave)

    token = create_access_token(user_id=123)

    payload = jwt.decode(token, otra_clave, algorithms=[ALGORITHM])
    assert payload["sub"] == "123"


def test_token_no_se_puede_verificar_con_otra_clave(monkeypatch):
    """
    Reverso del test anterior: un token firmado con la clave de settings
    no se puede verificar con ninguna otra clave.
    """
    monkeypatch.setattr(settings, "SECRET_KEY", "secret-de-prueba")

    token = create_access_token(user_id=123)

    # pytest.raises: afirma que ese bloque tiene que explotar con
    # exactamente esa excepción.
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, "otra-clave-que-no-es", algorithms=[ALGORITHM])