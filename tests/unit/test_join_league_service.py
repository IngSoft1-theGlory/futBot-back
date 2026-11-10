"""
Tests de join_league (service de ligas): unirse a una liga con equipo y alineación.
Cada test de error parte de un caso VÁLIDO y cambia UNA sola cosa.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from src.core.exceptions import AppError
from src.core.security import create_join_token, hash_password
from src.models import Behavior, LeagueStatus, LineupEntry, Player
from src.models.league import League
from src.schemas.league import JoinLeagueRequest
from src.services.league_service import join_league
from src.services.user_service import create_user_with_team
from src.realtime.event_bus import event_bus

from tests.unit.test_post_friendly_endpoint import client, comportamiento, db, headers

def crear_usuario(session, nombre):
    return create_user_with_team(
        session,
        username=nombre,
        email=f"{nombre}@famaf.unc.edu.ar",
        password="Password123!",
        team_data={"team_name": f"{nombre}FC", "team_logo": "https://example.com/logo.png"},
    )


def crear_jugadores(session, team_id):
    jugadores = []
    for n in range(1, 7):
        jugador = Player(
            team_id=team_id, name=f"Jugador {n}", number=n,
            power=50, agility=50, control=50, speed=50, strength=50,
        )
        session.add(jugador)
        jugadores.append(jugador)
    session.commit()
    return jugadores


def armar_body(usuario, jugadores, join_token=None):
    ids = [j.player_id for j in jugadores]
    return JoinLeagueRequest(
        team_id=usuario.team_id,
        join_token=join_token,
        formation_type="2-1",
        starting_players=[
            {"player_id": ids[0], "role": "DEF_LEFT", "behavior_id": 1},
            {"player_id": ids[1], "role": "DEF_RIGHT", "behavior_id": 1},
            {"player_id": ids[2], "role": "FORWARD", "behavior_id": 1},
        ],
        substitute_players=[{"player_id": i, "behavior_id": 1} for i in ids[3:]],
    )


@pytest.fixture()
def anfitrion(session):
    session.add(Behavior(name="Neutro", description="Se queda quieto", code="-", is_default=True))
    session.commit()
    return crear_usuario(session, "host")


@pytest.fixture()
def jugador(session):
    """Usuario que se une, con sus 6 jugadores."""
    usuario = crear_usuario(session, "rival")
    return usuario, crear_jugadores(session, usuario.team_id)


def crear_liga(session, anfitrion, contrasena=None, max_teams=4, status=LeagueStatus.PENDING):
    liga = League(
        league_name="Liga test", max_teams=max_teams,
        password_hash=hash_password(contrasena) if contrasena else None,
        host_team_id=anfitrion.team_id, match_duration=2, status=status,
    )
    session.add(liga)
    session.flush()
    # el anfitrión ya está inscripto: tiene su alineación en la liga
    for j in crear_jugadores(session, anfitrion.team_id):
        session.add(LineupEntry(
            league_id=liga.league_id, team_id=anfitrion.team_id, player_id=j.player_id,
            behavior_id=1, role=None, is_starter=False,
        ))
    session.commit()
    return liga


def entradas(session, league_id, team_id):
    return session.scalars(
        select(LineupEntry).where(LineupEntry.league_id == league_id, LineupEntry.team_id == team_id)
    ).all()


def test_deberia_inscribir_el_equipo_en_una_liga_publica_con_su_alineacion(session, anfitrion, jugador):
    usuario, jugadores = jugador
    liga = crear_liga(session, anfitrion)

    join_league(session, usuario.user_id, liga.league_id, armar_body(usuario, jugadores))

    guardadas = entradas(session, liga.league_id, usuario.team_id)
    assert len(guardadas) == 6
    assert sum(e.is_starter for e in guardadas) == 3


def test_deberia_inscribir_el_equipo_en_una_liga_privada_con_token_valido(session, anfitrion, jugador):
    usuario, jugadores = jugador
    liga = crear_liga(session, anfitrion, contrasena="clave123")
    token = create_join_token(usuario.user_id, liga.league_id)

    join_league(session, usuario.user_id, liga.league_id, armar_body(usuario, jugadores, token))

    assert len(entradas(session, liga.league_id, usuario.team_id)) == 6


def test_deberia_dar_404_si_la_liga_no_existe(session, anfitrion, jugador):
    usuario, jugadores = jugador

    with pytest.raises(AppError) as error:
        join_league(session, usuario.user_id, 9999, armar_body(usuario, jugadores))

    assert error.value.status_code == 404
    assert error.value.error_code == "NOT_FOUND"


def test_deberia_dar_400_league_unavailable_si_la_liga_ya_fue_iniciada(session, anfitrion, jugador):
    usuario, jugadores = jugador
    liga = crear_liga(session, anfitrion, status=LeagueStatus.IN_PROGRESS)

    with pytest.raises(AppError) as error:
        join_league(session, usuario.user_id, liga.league_id, armar_body(usuario, jugadores))

    assert error.value.status_code == 400
    assert error.value.error_code == "LEAGUE_UNAVAILABLE"


def test_deberia_dar_409_league_full_si_la_liga_alcanzo_su_cupo(session, anfitrion, jugador):
    usuario, jugadores = jugador
    liga = crear_liga(session, anfitrion, max_teams=4)
    # se llenan los 3 lugares restantes con equipos ya inscriptos
    for n in range(3):
        otro = crear_usuario(session, f"otro{n}")
        for j in crear_jugadores(session, otro.team_id):
            session.add(LineupEntry(
                league_id=liga.league_id, team_id=otro.team_id, player_id=j.player_id,
                behavior_id=1, role=None, is_starter=False,
            ))
    session.commit()

    with pytest.raises(AppError) as error:
        join_league(session, usuario.user_id, liga.league_id, armar_body(usuario, jugadores))

    assert error.value.status_code == 409
    assert error.value.error_code == "LEAGUE_FULL"


def test_deberia_dar_403_join_token_required_si_la_liga_es_privada_y_no_hay_token(session, anfitrion, jugador):
    usuario, jugadores = jugador
    liga = crear_liga(session, anfitrion, contrasena="clave123")

    with pytest.raises(AppError) as error:
        join_league(session, usuario.user_id, liga.league_id, armar_body(usuario, jugadores))

    assert error.value.status_code == 403
    assert error.value.error_code == "JOIN_TOKEN_REQUIRED"


def test_deberia_dar_403_join_token_expired_si_el_token_vencio(session, anfitrion, jugador):
    usuario, jugadores = jugador
    liga = crear_liga(session, anfitrion, contrasena="clave123")
    token = create_join_token(usuario.user_id, liga.league_id, expires_delta=timedelta(seconds=-10))

    with pytest.raises(AppError) as error:
        join_league(session, usuario.user_id, liga.league_id, armar_body(usuario, jugadores, token))

    assert error.value.status_code == 403
    assert error.value.error_code == "JOIN_TOKEN_EXPIRED"


@pytest.mark.parametrize("token", ["no-es-un-token", None])
def test_deberia_dar_403_invalid_join_token_si_el_token_es_basura_o_de_otra_liga_u_otro_usuario(
    session, anfitrion, jugador, token
):
    usuario, jugadores = jugador
    liga = crear_liga(session, anfitrion, contrasena="clave123")
    if token is None:
        token = create_join_token(usuario.user_id, liga.league_id + 1)  # emitido para otra liga

    with pytest.raises(AppError) as error:
        join_league(session, usuario.user_id, liga.league_id, armar_body(usuario, jugadores, token))

    assert error.value.status_code == 403
    assert error.value.error_code == "INVALID_JOIN_TOKEN"


def test_deberia_dar_403_invalid_join_token_si_el_token_es_de_otro_usuario(session, anfitrion, jugador):
    usuario, jugadores = jugador
    liga = crear_liga(session, anfitrion, contrasena="clave123")
    token = create_join_token(anfitrion.user_id, liga.league_id)

    with pytest.raises(AppError) as error:
        join_league(session, usuario.user_id, liga.league_id, armar_body(usuario, jugadores, token))

    assert error.value.status_code == 403
    assert error.value.error_code == "INVALID_JOIN_TOKEN"


def test_deberia_dar_409_already_joined_si_el_equipo_ya_esta_inscripto(session, anfitrion, jugador):
    usuario, jugadores = jugador
    liga = crear_liga(session, anfitrion)
    join_league(session, usuario.user_id, liga.league_id, armar_body(usuario, jugadores))

    with pytest.raises(AppError) as error:
        join_league(session, usuario.user_id, liga.league_id, armar_body(usuario, jugadores))

    assert error.value.status_code == 409
    assert error.value.error_code == "ALREADY_JOINED"


def test_deberia_dar_400_invalid_lineup_y_no_guardar_nada_si_la_alineacion_es_invalida(session, anfitrion, jugador):
    usuario, jugadores = jugador
    liga = crear_liga(session, anfitrion)
    body = armar_body(usuario, jugadores)
    body.starting_players[1].role = "DEF_LEFT"  # rol repetido

    with pytest.raises(AppError) as error:
        join_league(session, usuario.user_id, liga.league_id, body)

    assert error.value.status_code == 400
    assert error.value.error_code == "INVALID_LINEUP"
    assert entradas(session, liga.league_id, usuario.team_id) == []


def test_deberia_dar_403_si_el_equipo_no_pertenece_al_usuario(session, anfitrion, jugador):
    usuario, jugadores = jugador
    liga = crear_liga(session, anfitrion)
    body = armar_body(usuario, jugadores)
    body.team_id = anfitrion.team_id  # equipo de otro usuario

    with pytest.raises(AppError) as error:
        join_league(session, usuario.user_id, liga.league_id, body)

    assert error.value.status_code == 403

def test_deberia_publicar_team_joined_league_si_el_equipo_se_une(client, db, comportamiento):
    liga = crear_liga(db, crear_usuario(db, "host"))
    usuario = crear_usuario(db, "rival")
    body = armar_body(usuario, crear_jugadores(db, usuario.team_id))
    # Suscribe el test para capturar los eventos publicados en el bus de eventos
    queue = event_bus.subscribe()
    try:
        # El equipo solicita unirse a la liga mediante el endpoint, guardando la respuesta en `r`
        r = client.post(f"/api/v1/leagues/{liga.league_id}/teams", json=body.model_dump(), headers=headers(usuario))
        assert r.status_code == 201
        # Lee los eventos recibidos y luego se valida su contenido.
        eventos = [queue.get_nowait() for _ in range(queue.qsize())]
    finally:
        # Evita que la suscripción afecte a otros tests.
        event_bus.unsubscribe(queue)
 
    assert eventos == [{
        "event": "TEAM_JOINED_LEAGUE",
        "data": {"league_id": liga.league_id, "team_id": usuario.team_id},
    }]
 
 
def test_no_deberia_publicar_nada_si_la_liga_no_existe(client, db, comportamiento):
    usuario = crear_usuario(db, "rival")
    body = armar_body(usuario, crear_jugadores(db, usuario.team_id))
    # Suscribe el test para comprobar que no se emitan eventos.
    queue = event_bus.subscribe()
    try:
        # Intenta unirse a una liga inexistente.
        r = client.post("/api/v1/leagues/9999/teams", json=body.model_dump(), headers=headers(usuario))
        assert r.status_code == 404
        assert queue.qsize() == 0
    finally:
        # Libera la suscripción para no afectar otros tests.
        event_bus.unsubscribe(queue)
