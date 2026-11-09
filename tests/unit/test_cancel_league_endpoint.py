"""
Tests de cancel_league (service de ligas). Sin HTTP: se llama al service directo.
Los errores se verifican con el status_code y el error_code de la excepción,
que son los que el handler convierte en la respuesta.
"""

import pytest

from src.core.exceptions import AppError
from src.models import LeagueStatus
from src.models.league import League
from src.services.league_service import cancel_league, join_league

# reutilizo fixtures y helpers
from tests.unit.test_join_league_service import anfitrion, armar_body, crear_liga, entradas, jugador 

def test_deberia_borrar_la_liga_y_todas_sus_inscripciones(session, anfitrion, jugador):
    usuario, jugadores = jugador
    liga = crear_liga(session, anfitrion)
    join_league(session, usuario.user_id, liga.league_id, armar_body(usuario, jugadores))
    league_id = liga.league_id 
    assert len(entradas(session, league_id, anfitrion.team_id)) == 6   # antes: anfitrión inscripto
    assert len(entradas(session, league_id, usuario.team_id)) == 6     # antes: invitado inscripto

    cancel_league(session, anfitrion.user_id, league_id)

    assert session.get(League, league_id) is None
    assert entradas(session, league_id, anfitrion.team_id) == []
    assert entradas(session, league_id, usuario.team_id) == []


def test_deberia_lanzar_404_league_not_found_si_la_liga_no_existe(session, anfitrion):
    with pytest.raises(AppError) as error:
        cancel_league(session, anfitrion.user_id, 9999)

    assert error.value.status_code == 404
    assert error.value.error_code == "LEAGUE_NOT_FOUND"


def test_deberia_lanzar_403_not_league_host_y_no_borrar_si_no_es_el_anfitrion(session, anfitrion, jugador):
    usuario, _ = jugador  # tiene equipo, pero no es el anfitrión
    liga = crear_liga(session, anfitrion)

    with pytest.raises(AppError) as error:
        cancel_league(session, usuario.user_id, liga.league_id)

    assert error.value.status_code == 403
    assert error.value.error_code == "NOT_LEAGUE_HOST"
    assert session.get(League, liga.league_id) is not None
    assert len(entradas(session, liga.league_id, anfitrion.team_id)) == 6


def test_deberia_lanzar_409_league_already_started_y_no_borrar_si_la_liga_no_esta_pending(session, anfitrion):
    liga = crear_liga(session, anfitrion, status=LeagueStatus.IN_PROGRESS)

    with pytest.raises(AppError) as error:
        cancel_league(session, anfitrion.user_id, liga.league_id)

    assert error.value.status_code == 409
    assert error.value.error_code == "LEAGUE_ALREADY_STARTED"
    assert session.get(League, liga.league_id) is not None
    assert len(entradas(session, liga.league_id, anfitrion.team_id)) == 6