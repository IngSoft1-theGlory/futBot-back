"""
Tests de create_league (service de ligas)
"""

from __future__ import annotations

import pytest

from src.core.exceptions import AppError
from src.core.security import verify_password
from src.models import Behavior, LeagueStatus, Player
from src.schemas.league import CreateLeagueRequest
from src.services.league_service import create_league
from src.services.user_service import create_user_with_team


@pytest.fixture()
def usuario(session):
    return create_user_with_team(
        session,
        username="Maradona10",
        email="diego@famaf.unc.edu.ar",
        password="Password123!",
        team_data={"team_name": "alfajoresFC", "team_logo": "https://example.com/logos/alfajores.png"},
    )


@pytest.fixture()
def payload(session, usuario):
    # 6 jugadores del equipo y un comportamiento predeterminado.
    for n in range(1, 7):
        session.add(Player(
            team_id=usuario.team_id, name=f"Jugador {n}", number=n,
            power=50, agility=50, control=50, speed=50, strength=50,
        ))
    session.add(Behavior(name="Neutro", description="Se queda quieto", code="-", is_default=True))
    session.commit()

    # lo que manda el cliente: una liga pública válida
    return CreateLeagueRequest(
        team_id=usuario.team_id,
        league_name="Liga de prueba",
        match_duration=5,
        max_teams=8,
        password=None,
        formation_type="2-1",
        starting_players=[
            {"player_id": 1, "role": "DEF_LEFT", "behavior_id": 1},
            {"player_id": 2, "role": "DEF_RIGHT", "behavior_id": 1},
            {"player_id": 3, "role": "FORWARD", "behavior_id": 1},
        ],
        substitute_players=[
            {"player_id": 4, "behavior_id": 1},
            {"player_id": 5, "behavior_id": 1},
            {"player_id": 6, "behavior_id": 1},
        ],
    )


def test_deberia_crear_liga_publica_pendiente_si_los_datos_son_validos(session, usuario, payload):
    liga = create_league(session, usuario.user_id, payload)

    assert liga.status == LeagueStatus.PENDING
    assert liga.host_team_id == usuario.team_id
    assert liga.password_hash is None  # sin contraseña es publica


def test_deberia_guardar_la_contrasena_hasheada_si_la_liga_es_privada(session, usuario, payload):
    payload.password = "Asado123"

    liga = create_league(session, usuario.user_id, payload)

    assert liga.password_hash != "Asado123"  # chequeo q no se guarda en texto plano
    assert verify_password("Asado123", liga.password_hash)  # es el hash de esa contraseña


def test_deberia_responder_400_invalid_league_capacity_si_el_cupo_es_impar(session, usuario, payload):
    payload.max_teams = 7

    with pytest.raises(AppError) as error:
        create_league(session, usuario.user_id, payload)

    assert error.value.status_code == 400
    assert error.value.error_code == "INVALID_LEAGUE_CAPACITY"


def test_deberia_responder_400_invalid_settings_si_la_duracion_no_es_2_ni_5(session, usuario, payload):
    payload.match_duration = 3

    with pytest.raises(AppError) as error:
        create_league(session, usuario.user_id, payload)

    assert error.value.status_code == 400
    assert error.value.error_code == "INVALID_SETTINGS"


def test_deberia_responder_400_invalid_configuration_si_la_alineacion_es_invalida(session, usuario, payload):
    payload.starting_players[1].role = "DEF_LEFT"  # rol repetido

    with pytest.raises(AppError) as error:
        create_league(session, usuario.user_id, payload)

    assert error.value.status_code == 400
    assert error.value.error_code == "INVALID_CONFIGURATION"