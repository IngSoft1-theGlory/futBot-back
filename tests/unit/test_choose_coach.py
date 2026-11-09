"""Tests de elegir el DT de la liga. Un test por criterio de aceptación."""

import pytest

from src.core.exceptions import InvalidData, LeagueNotInProgressError
from src.engine._02_to_match.state import coach_registry
from src.models import BehaviorType, LeagueStatus
from src.schemas.league import ChooseCoachRequest
from src.services.coach_service import choose_coach_behavior

# reutilizo fixtures y helpers de otros tests
from tests.unit.test_behavior_type import crear_en_base
from tests.unit.test_join_league_service import anfitrion, crear_liga, crear_usuario


def elegir(session, usuario, liga, behavior_id):
    return choose_coach_behavior(
        session, league_id=liga.league_id, user_id=usuario.user_id,
        team_id=usuario.team_id, payload=ChooseCoachRequest(behavior_id=behavior_id),
    )


def test_deberia_guardar_el_dt_elegido_sin_afectar_otros_equipos_ni_ligas(session, anfitrion):
    coach_registry._coaches.clear()  # el registro es global y los ids se repiten en cada test
    otro = crear_usuario(session, "otro")
    liga = crear_liga(session, anfitrion, status=LeagueStatus.IN_PROGRESS)
    otra_liga = crear_liga(session, otro, status=LeagueStatus.IN_PROGRESS)
    dt = crear_en_base(session, anfitrion.user_id, BehaviorType.COACH)

    elegir(session, anfitrion, liga, dt.behavior_id)

    assert coach_registry.get(liga.league_id, anfitrion.team_id) == dt.behavior_id
    assert coach_registry.get(liga.league_id, otro.team_id) is None            # otro equipo
    assert coach_registry.get(otra_liga.league_id, anfitrion.team_id) is None  # otra liga


def test_deberia_dejar_al_equipo_sin_dt_si_behavior_id_es_none(session, anfitrion):
    coach_registry._coaches.clear()
    liga = crear_liga(session, anfitrion, status=LeagueStatus.IN_PROGRESS)
    dt = crear_en_base(session, anfitrion.user_id, BehaviorType.COACH)
    elegir(session, anfitrion, liga, dt.behavior_id)

    elegir(session, anfitrion, liga, None)

    assert coach_registry.get(liga.league_id, anfitrion.team_id) is None # se quita el comportamiento de DT del equipo en la liga


def test_deberia_rechazar_un_comportamiento_que_no_es_coach(session, anfitrion):
    coach_registry._coaches.clear()
    liga = crear_liga(session, anfitrion, status=LeagueStatus.IN_PROGRESS)
    dt = crear_en_base(session, anfitrion.user_id, BehaviorType.COACH)
    de_jugador = crear_en_base(session, anfitrion.user_id, BehaviorType.PLAYER) 
    elegir(session, anfitrion, liga, dt.behavior_id) 
    with pytest.raises(InvalidData):
        elegir(session, anfitrion, liga, de_jugador.behavior_id) # reasigno con un comportamiento de jugador, no de DT


    assert coach_registry.get(liga.league_id, anfitrion.team_id) == dt.behavior_id  # sigue el comportamiento anterior


def test_deberia_rechazar_si_la_liga_no_esta_en_curso(session, anfitrion):
    coach_registry._coaches.clear()
    liga = crear_liga(session, anfitrion)  # por defecto queda en PENDING
    dt = crear_en_base(session, anfitrion.user_id, BehaviorType.COACH)

    with pytest.raises(LeagueNotInProgressError):
        elegir(session, anfitrion, liga, dt.behavior_id)

    assert coach_registry.get(liga.league_id, anfitrion.team_id) is None # no se guardo ningun comportamiento de DT porque la liga no estaba in_progress