"""
Tests de la opción de penales al crear una liga
"""

from src.models import League
from src.services.league_service import create_league
from src.services.match_start_service import prepare_match

# reutilizo fixtures de otros tests para no repetir código
from tests.unit.test_create_league_endpoint import payload, usuario 
from tests.unit.test_match_start_service import _armar_partido, comportamiento, partido  


# Crear la liga -----------------------------------------------------------


def test_deberia_crear_liga_con_penales_si_se_pidieron(session, usuario, payload):
    payload.penalties_enabled = True

    liga = create_league(session, usuario.user_id, payload)

    assert liga.penalties_enabled is True


def test_deberia_crear_liga_sin_penales_si_no_se_envia_el_campo(session, usuario, payload):
    liga = create_league(session, usuario.user_id, payload)

    assert liga.penalties_enabled is False


# Preparar el partido -----------------------------------------------------


def _partido_de_liga(session, comportamiento, con_penales):
    """Un partido armado como los demás, pero asociado a una liga."""
    partido = _armar_partido(session, comportamiento)
    liga = League(
        league_name="Liga", max_teams=4, match_duration=2,
        host_team_id=partido.team_host_id, penalties_enabled=con_penales,
    )
    session.add(liga)
    session.flush()
    partido.league_id = liga.league_id
    session.commit()
    return partido


def test_deberia_prepare_match_habilitar_los_penales_si_la_liga_los_tiene(session, comportamiento):
    partido = _partido_de_liga(session, comportamiento, con_penales=True)

    state = prepare_match(session, partido.match_id)

    assert state.penalties_enabled is True


def test_deberia_prepare_match_no_habilitar_los_penales_si_la_liga_no_los_tiene(session, comportamiento):
    partido = _partido_de_liga(session, comportamiento, con_penales=False)

    state = prepare_match(session, partido.match_id)

    assert state.penalties_enabled is False
