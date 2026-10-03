import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.config.settings import settings
from src.core.security import create_access_token, create_ws_global_token, decode_ws_global_token
from src.database.base import Base, get_db
from src.main import app
from src.models import Match, MatchStatus, Team, User


# --- Base y cliente (mismo patrón que test_post_friendly_endpoint.py) ---------------

@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys_on(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def client(db):
    def override_get_db():
        s = sessionmaker(bind=db.get_bind(), autoflush=False)()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- Helpers --------------------------------------------------------------------------

def _crear_usuario(db, n: int) -> User:
    user = User(
        username=f"user{n}", email=f"user{n}@example.com",
        password_hash="hash-falso", team=Team(team_name=f"Equipo {n}"),
    )
    db.add(user)
    db.commit()
    return user


def _crear_partido(db, host: User, away: User | None, status=MatchStatus.IN_PROGRESS) -> Match:
    match = Match(
        match_duration=2, status=status,
        team_host_id=host.team_id,
        team_away_id=away.team_id if away else None,
    )
    db.add(match)
    db.commit()
    return match


def _url(match_id) -> str:
    return f"/api/v1/matches/{match_id}/live-token"


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.user_id)}"}


# --- 200 -----------------------------------------------------------------------------

def test_deberia_devolver_credenciales_validas_para_el_anfitrion(client, db):
    host, away = _crear_usuario(db, 1), _crear_usuario(db, 2)
    match = _crear_partido(db, host, away)

    response = client.post(_url(match.match_id), headers=_auth(host))

    assert response.status_code == 200
    body = response.json()
    assert body["match_id"] == match.match_id
    assert body["expires_in_seconds"] == 60
    prefijo = f"{settings.WS_BASE_URL}/ws/v1/matches/{match.match_id}?token="
    assert body["websocket_url"].startswith(prefijo)
    # el token de la URL es de ESTE usuario y de ESTE partido
    token = body["websocket_url"].removeprefix(prefijo)
    assert decode_ws_global_token(token) == host.user_id


def test_deberia_devolver_credenciales_validas_para_el_visitante(client, db):
    host, away = _crear_usuario(db, 1), _crear_usuario(db, 2)
    match = _crear_partido(db, host, away)

    response = client.post(_url(match.match_id), headers=_auth(away))

    assert response.status_code == 200


# --- 401 -----------------------------------------------------------------------------

def test_deberia_devolver_401_sin_token(client, db):
    host, away = _crear_usuario(db, 1), _crear_usuario(db, 2)
    match = _crear_partido(db, host, away)

    response = client.post(_url(match.match_id))

    assert response.status_code == 401
    assert response.json()["error"] == "UNAUTHORIZED"


def test_deberia_devolver_401_si_el_token_no_es_de_login(client, db):
    host, away = _crear_usuario(db, 1), _crear_usuario(db, 2)
    match = _crear_partido(db, host, away)
    headers = {"Authorization": f"Bearer {create_ws_global_token(host.user_id)}"}

    response = client.post(_url(match.match_id), headers=headers)

    assert response.status_code == 401


def test_deberia_devolver_401_si_el_usuario_fue_borrado_con_token_vigente(client, db):
    host, away, otro = _crear_usuario(db, 1), _crear_usuario(db, 2), _crear_usuario(db, 3)
    match = _crear_partido(db, host, away)
    headers = _auth(otro)          # token emitido ANTES de borrar
    db.delete(otro)
    db.commit()

    response = client.post(_url(match.match_id), headers=headers)

    assert response.status_code == 401


# --- 404 -----------------------------------------------------------------------------

def test_deberia_devolver_404_si_el_partido_no_existe(client, db):
    user = _crear_usuario(db, 1)

    response = client.post(_url(999), headers=_auth(user))

    assert response.status_code == 404
    assert response.json()["error"] == "MATCH_NOT_FOUND"


def test_deberia_devolver_404_si_el_partido_esta_pending(client, db):
    host = _crear_usuario(db, 1)
    match = _crear_partido(db, host, None, MatchStatus.PENDING)

    response = client.post(_url(match.match_id), headers=_auth(host))

    assert response.status_code == 404
    assert response.json()["error"] == "MATCH_NOT_FOUND"


def test_deberia_devolver_404_si_el_partido_esta_finished(client, db):
    host, away = _crear_usuario(db, 1), _crear_usuario(db, 2)
    match = _crear_partido(db, host, away, MatchStatus.FINISHED)

    response = client.post(_url(match.match_id), headers=_auth(host))

    assert response.status_code == 404
    assert response.json()["error"] == "MATCH_NOT_FOUND"


# --- 403 y 422 -----------------------------------------------------------------------

def test_deberia_devolver_403_si_el_usuario_no_participa(client, db):
    host, away, otro = _crear_usuario(db, 1), _crear_usuario(db, 2), _crear_usuario(db, 3)
    match = _crear_partido(db, host, away)

    response = client.post(_url(match.match_id), headers=_auth(otro))

    assert response.status_code == 403
    assert response.json()["error"] == "UNAUTHORIZED_ACTION"


def test_deberia_devolver_422_si_el_match_id_no_es_numerico(client, db):
    user = _crear_usuario(db, 1)

    response = client.post(_url("abc"), headers=_auth(user))

    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"
    