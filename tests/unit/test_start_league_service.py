"""
Tests de start_league y del inicio automatico de join_league (service de ligas)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from src.core.exceptions import AppError
from src.models import Behavior, LeagueStatus, LineupEntry, Match
from src.schemas.league import StartLeagueRequest
from src.services.league_service import join_league, start_league

# Helpers que ya existen en los tests de join_league
from tests.unit.test_join_league_service import armar_body, crear_jugadores, crear_liga, crear_usuario


@pytest.fixture()
def anfitrion(session):
    # los LineupEntry necesitan un comportamiento con id 1
    session.add(Behavior(name="Neutro", description="Se queda quieto", code="-", is_default=True))
    session.commit()
    return crear_usuario(session, "host")


def inscribir_equipos(session, liga, cantidad):
    """Suma cantidad equipos mas a la liga (cada uno con sus 6 jugadores)"""
    for n in range(cantidad):
        usuario = crear_usuario(session, f"equipo{n}")
        # crear_jugadores (del otro archivo) crea los 6 jugadores del equipo
        # Por cada uno se agrega una fila en lineup_entries: asi el equipo queda inscripto en la liga
        for jugador in crear_jugadores(session, usuario.team_id):
            session.add(LineupEntry(
                league_id=liga.league_id, team_id=usuario.team_id, player_id=jugador.player_id,
                behavior_id=1, role=None, is_starter=False,
            ))
    session.commit()


def contar_partidos(session, liga):
    return session.scalar(select(func.count()).select_from(Match).where(Match.league_id == liga.league_id))


def assert_liga_sin_cambios(session, liga, estado):
    session.refresh(liga)
    assert liga.status == estado
    assert contar_partidos(session, liga) == 0  # no se creo el fixture


def test_deberia_iniciar_la_liga_y_crear_su_fixture(session, anfitrion):
    liga = crear_liga(session, anfitrion)  # max_teams=4, ya tiene al anfitrion
    inscribir_equipos(session, liga, 3)    # ahora hay 4 equipos

    resultado = start_league(session, anfitrion.user_id, liga.league_id)

    assert resultado.status == LeagueStatus.IN_PROGRESS
    assert contar_partidos(session, liga) == 6  # 4 equipos: 4*3/2 partidos


def test_deberia_responder_404_league_not_found_si_la_liga_no_existe(session, anfitrion):
    # start_league debe que lanzar un AppError, sino lo lanza el test falla
    # ademas se guarda en error para despues revisar su codigo.
    with pytest.raises(AppError) as error:
        start_league(session, anfitrion.user_id, 9999)

    assert error.value.status_code == 404
    assert error.value.error_code == "LEAGUE_NOT_FOUND"


def test_deberia_responder_403_si_el_usuario_no_es_el_anfitrion(session, anfitrion):
    liga = crear_liga(session, anfitrion)
    inscribir_equipos(session, liga, 3)
    otro = crear_usuario(session, "otro")

    # se espera tambien un error, pero porque otro no es el anfitrion
    with pytest.raises(AppError) as error:
        start_league(session, otro.user_id, liga.league_id)

    assert error.value.status_code == 403
    assert error.value.error_code == "UNAUTHORIZED_ACTION"
    assert_liga_sin_cambios(session, liga, LeagueStatus.PENDING)


@pytest.mark.parametrize("equipos, estado, codigo, error_esperado", [
    (4, LeagueStatus.IN_PROGRESS, 409, "LEAGUE_ALREADY_STARTED"),
    (2, LeagueStatus.PENDING, 400, "INSUFFICIENT_TEAMS"),
    (5, LeagueStatus.PENDING, 400, "ODD_TEAMS_COUNT"),
])
def test_no_deberia_iniciar_la_liga_si_no_cumple_las_reglas(session, anfitrion, equipos, estado, codigo, error_esperado):
    liga = crear_liga(session, anfitrion, max_teams=12, status=estado)
    inscribir_equipos(session, liga, equipos - 1)  # con el anfitrion ya cuenta como uno

    # en cada caso del parametrize tiene que saltar un error distinto
    with pytest.raises(AppError) as error:
        start_league(session, anfitrion.user_id, liga.league_id)

    assert error.value.status_code == codigo
    assert error.value.error_code == error_esperado
    assert_liga_sin_cambios(session, liga, estado)


def test_deberia_rechazar_un_status_distinto_de_in_progress():
    # con el Literal[IN_PROGRESS] hace que cualquier otro valor tire ValidationError
    with pytest.raises(ValidationError):
        StartLeagueRequest(status="FINISHED")


def test_deberia_iniciar_la_liga_sola_si_el_equipo_que_se_une_completa_el_cupo(session, anfitrion):
    liga = crear_liga(session, anfitrion, max_teams=4) # 1 de 4
    inscribir_equipos(session, liga, 2)  # 3 de 4
    rival = crear_usuario(session, "rival") # 4 de 4
    body = armar_body(rival, crear_jugadores(session, rival.team_id))

    resultado = join_league(session, rival.user_id, liga.league_id, body)

    assert resultado.status == LeagueStatus.IN_PROGRESS
    assert contar_partidos(session, liga) == 6 # 4 equipos: 4*3/2 partidos


def test_deberia_seguir_pending_si_el_equipo_que_se_une_no_completa_el_cupo(session, anfitrion):
    liga = crear_liga(session, anfitrion, max_teams=4)
    inscribir_equipos(session, liga, 1)  # 2 de 4, con el rival serian 3
    rival = crear_usuario(session, "rival")
    body = armar_body(rival, crear_jugadores(session, rival.team_id))

    resultado = join_league(session, rival.user_id, liga.league_id, body)

    assert resultado.status == LeagueStatus.PENDING
    assert contar_partidos(session, liga) == 0