from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

from src.core.security import create_access_token, create_ws_global_token
from src.database.base import Base, get_db
from src.main import app
from src.models import Match, MatchStatus, Team, User



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


def _ws(match_id, token) -> str:
    return f"/ws/v1/matches/{match_id}?token={token}"


def _assert_rechazada(client, url):
    """El handshake se rechaza (cierre 1008 antes del accept)."""
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(url):
            pass
    assert exc.value.code == 1008



def test_deberia_aceptar_conexion_del_anfitrion(client, db):
    host, away = _crear_usuario(db, 1), _crear_usuario(db, 2)
    match = _crear_partido(db, host, away)
    token = create_ws_global_token(host.user_id)
    with client.websocket_connect(_ws(match.match_id, token)):
        pass


def test_deberia_aceptar_conexion_del_visitante(client, db):
    host, away = _crear_usuario(db, 1), _crear_usuario(db, 2)
    match = _crear_partido(db, host, away)
    token = create_ws_global_token(away.user_id)
    with client.websocket_connect(_ws(match.match_id, token)):
        pass


def test_deberia_aceptar_el_mismo_token_en_cualquier_partido_donde_participa(client, db):
    """Opción A: el token no está atado a un partido; manda la revalidación contra la DB."""
    host, away = _crear_usuario(db, 1), _crear_usuario(db, 2)
    partido_a = _crear_partido(db, host, away)
    partido_b = _crear_partido(db, host, away)
    token = create_ws_global_token(host.user_id)
    with client.websocket_connect(_ws(partido_a.match_id, token)):
        pass
    with client.websocket_connect(_ws(partido_b.match_id, token)):
        pass


def test_deberia_aceptar_dos_conexiones_simultaneas_del_mismo_usuario(client, db):
    host, away = _crear_usuario(db, 1), _crear_usuario(db, 2)
    match = _crear_partido(db, host, away)
    token = create_ws_global_token(host.user_id)
    with client.websocket_connect(_ws(match.match_id, token)):
        with client.websocket_connect(_ws(match.match_id, token)):
            pass


def test_deberia_ignorar_lo_que_manda_el_cliente_incluidos_frames_binarios(client, db):
    host, away = _crear_usuario(db, 1), _crear_usuario(db, 2)
    match = _crear_partido(db, host, away)
    token = create_ws_global_token(host.user_id)
    with client.websocket_connect(_ws(match.match_id, token)) as ws:
        ws.send_bytes(b"\x00\x01")
        ws.send_text("hola")
    # si el server hubiera reventado, TestClient re-lanza el error al salir del with



def test_deberia_rechazar_conexion_sin_token(client, db):
    host, away = _crear_usuario(db, 1), _crear_usuario(db, 2)
    match = _crear_partido(db, host, away)
    _assert_rechazada(client, f"/ws/v1/matches/{match.match_id}")


def test_deberia_rechazar_token_mal_formado(client, db):
    host, away = _crear_usuario(db, 1), _crear_usuario(db, 2)
    match = _crear_partido(db, host, away)
    _assert_rechazada(client, _ws(match.match_id, "esto.no.es.un.jwt"))


def test_deberia_rechazar_token_vencido(client, db):
    host, away = _crear_usuario(db, 1), _crear_usuario(db, 2)
    match = _crear_partido(db, host, away)
    token = create_ws_global_token(host.user_id, expires_delta=timedelta(seconds=-1))
    _assert_rechazada(client, _ws(match.match_id, token))


def test_deberia_rechazar_token_de_login(client, db):
    host, away = _crear_usuario(db, 1), _crear_usuario(db, 2)
    match = _crear_partido(db, host, away)
    _assert_rechazada(client, _ws(match.match_id, create_access_token(host.user_id)))



def test_deberia_rechazar_partido_inexistente(client, db):
    host = _crear_usuario(db, 1)
    _assert_rechazada(client, _ws(999, create_ws_global_token(host.user_id)))


@pytest.mark.parametrize("estado", [MatchStatus.PENDING, MatchStatus.FINISHED])
def test_deberia_rechazar_partido_que_no_esta_en_curso(client, db, estado):
    host, away = _crear_usuario(db, 1), _crear_usuario(db, 2)
    match = _crear_partido(db, host, away if estado == MatchStatus.FINISHED else None, estado)
    token = create_ws_global_token(host.user_id)
    _assert_rechazada(client, _ws(match.match_id, token))


def test_deberia_rechazar_usuario_que_no_participa(client, db):
    host, away, otro = _crear_usuario(db, 1), _crear_usuario(db, 2), _crear_usuario(db, 3)
    match = _crear_partido(db, host, away)
    token = create_ws_global_token(otro.user_id)
    _assert_rechazada(client, _ws(match.match_id, token))


def test_deberia_rechazar_usuario_que_juega_otro_partido(client, db):
    """Con A es la barrera clave: un token válido no abre partidos ajenos."""
    a, b, c, d = (_crear_usuario(db, n) for n in (1, 2, 3, 4))
    _crear_partido(db, a, b)
    partido_cd = _crear_partido(db, c, d)
    token = create_ws_global_token(a.user_id)
    _assert_rechazada(client, _ws(partido_cd.match_id, token))


def test_deberia_rechazar_usuario_borrado_con_token_vigente(client, db):
    host, away, otro = _crear_usuario(db, 1), _crear_usuario(db, 2), _crear_usuario(db, 3)
    match = _crear_partido(db, host, away)
    token = create_ws_global_token(otro.user_id)
    db.delete(otro)
    db.commit()
    _assert_rechazada(client, _ws(match.match_id, token))


def test_deberia_rechazar_match_id_no_numerico(client, db):
    host = _crear_usuario(db, 1)
    token = create_ws_global_token(host.user_id)
    _assert_rechazada(client, f"/ws/v1/matches/abc?token={token}")