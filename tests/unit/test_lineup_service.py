"""
Tests simples del service de lineup (src/services/lineup_service.py).

Se llaman las funciones directamente, sin pasar por el endpoint.
Cada test de "falla" parte de una alineación válida y cambia UNA sola cosa,
así se sabe que falla por ese motivo y no por otro.
"""

import pytest
from sqlalchemy import select

from src.core.exceptions import (
    ForbiddenError,
    InvalidConfigurationError,
    InvalidSettingsError,
    PreconditionFailedError,
)
from src.models import Behavior, LineupEntry, Match, MatchStatus, Player, Team
from src.schemas.lineup_config import LineupConfig, StartingPlayer, SubstitutePlayer
from src.services.lineup_service import (
    save_lineup,
    validate_lineup,
    validate_match_duration,
    validate_min_players,
    validate_team_belongs_to_user,
)


# --- Datos de base para los tests ------------------------------------------------
# Una entry necesita partido, equipo, jugador y comportamiento reales (por las FKs).
# Un fixture es una funcion que prepara datos: el test que pide su nombre como
# parametro lo recibe ya armado.

@pytest.fixture()
def local(session):
    # Equipo anfitrion. commit() para que la base le asigne su team_id.
    equipo = Team(team_name="Local FC")
    session.add(equipo)
    session.commit()
    return equipo


@pytest.fixture()
def visitante(session):
    # Equipo rival.
    equipo = Team(team_name="Visitante FC")
    session.add(equipo)
    session.commit()
    return equipo


@pytest.fixture()
def partido(session, local, visitante):
    # Partido entre los dos equipos (pide los fixtures local y visitante).
    match = Match(
        team_host_id=local.team_id,
        team_away_id=visitante.team_id,
        match_duration=5,
        status=MatchStatus.IN_PROGRESS,
    )
    session.add(match)
    session.commit()
    return match


@pytest.fixture()
def comportamiento(session):
    behavior = Behavior(name="Patear", description="Patea la pelota", code="def on_tick(api): pass", is_default=True)
    session.add(behavior)
    session.commit()
    return behavior


def crear_jugadores(session, equipo, cantidad=6):
    """Crea `cantidad` jugadores del equipo."""
    jugadores = [
        Player(
            team_id=equipo.team_id,
            name=f"Jugador {n}",
            number=n,
            power=60, agility=60, control=60, speed=60, strength=60,
        )
        for n in range(1, cantidad + 1)
    ]
    session.add_all(jugadores)
    session.commit()
    return jugadores


def armar_config(jugadores, comportamiento):
    """Arma una alineación VÁLIDA: formación 2-1, jugadores 1-3 titulares y 4-6 suplentes."""
    b = comportamiento.behavior_id
    return LineupConfig(
        formation_type="2-1",
        starting_players=[
            StartingPlayer(player_id=jugadores[0].player_id, role="DEF_LEFT", behavior_id=b),
            StartingPlayer(player_id=jugadores[1].player_id, role="DEF_RIGHT", behavior_id=b),
            StartingPlayer(player_id=jugadores[2].player_id, role="FORWARD", behavior_id=b),
        ],
        substitute_players=[
            SubstitutePlayer(player_id=jugadores[3].player_id, behavior_id=b),
            SubstitutePlayer(player_id=jugadores[4].player_id, behavior_id=b),
            SubstitutePlayer(player_id=jugadores[5].player_id, behavior_id=b),
        ],
    )


def test_deberia_aceptar_un_equipo_que_pertenece_al_usuario(session, usuario_con_equipo):
    # no tiene que lanzar ningún error
    validate_team_belongs_to_user(session, usuario_con_equipo.user_id, usuario_con_equipo.team_id)


def test_deberia_fallar_si_el_equipo_no_pertenece_al_usuario(session, usuario_con_equipo, local):
    # "local" es otro equipo, no el del usuario
    with pytest.raises(ForbiddenError):
        validate_team_belongs_to_user(session, usuario_con_equipo.user_id, local.team_id)


@pytest.mark.parametrize("duracion", [0, -5, 11])
def test_deberia_fallar_si_la_duracion_es_invalida(duracion):
    with pytest.raises(InvalidSettingsError):
        validate_match_duration(duracion)


def test_deberia_fallar_si_el_equipo_tiene_menos_de_6_jugadores(session, local):
    crear_jugadores(session, local, cantidad=5)
    with pytest.raises(PreconditionFailedError):
        validate_min_players(session, local.team_id)


def test_deberia_aceptar_una_alineacion_valida(session, local, comportamiento):
    # si esta falla, los tests de abajo no prueban lo que dicen probar
    jugadores = crear_jugadores(session, local)
    config = armar_config(jugadores, comportamiento)

    validate_lineup(session, config, jugadores)


def test_deberia_fallar_si_la_formacion_no_existe(session, local, comportamiento):
    jugadores = crear_jugadores(session, local)
    config = armar_config(jugadores, comportamiento)

    config.formation_type = "9-9"
    with pytest.raises(InvalidConfigurationError):
        validate_lineup(session, config, jugadores)


def test_deberia_fallar_si_no_hay_3_titulares_y_3_suplentes(session, local, comportamiento):
    jugadores = crear_jugadores(session, local)
    config = armar_config(jugadores, comportamiento)

    config.substitute_players.pop()  # quedan solo 2 suplentes
    with pytest.raises(InvalidConfigurationError):
        validate_lineup(session, config, jugadores)


def test_deberia_fallar_si_un_rol_esta_repetido(session, local, comportamiento):
    jugadores = crear_jugadores(session, local)
    config = armar_config(jugadores, comportamiento)

    # quedan DEF_LEFT, DEF_LEFT y FORWARD: falta DEF_RIGHT
    config.starting_players[1].role = "DEF_LEFT"
    with pytest.raises(InvalidConfigurationError):
        validate_lineup(session, config, jugadores)


def test_deberia_fallar_si_un_jugador_esta_repetido(session, local, comportamiento):
    jugadores = crear_jugadores(session, local)
    config = armar_config(jugadores, comportamiento)

    # un suplente con el mismo jugador que el primer titular
    config.substitute_players[0].player_id = config.starting_players[0].player_id
    with pytest.raises(InvalidConfigurationError):
        validate_lineup(session, config, jugadores)


def test_deberia_fallar_si_un_jugador_no_pertenece_al_equipo(session, local, visitante, comportamiento):
    jugadores = crear_jugadores(session, local)
    ajeno = crear_jugadores(session, visitante, cantidad=1)[0]  # jugador del otro equipo
    config = armar_config(jugadores, comportamiento)

    config.starting_players[0].player_id = ajeno.player_id
    with pytest.raises(InvalidConfigurationError):
        validate_lineup(session, config, jugadores)


def test_deberia_fallar_si_un_comportamiento_no_existe(session, local, comportamiento):
    jugadores = crear_jugadores(session, local)
    config = armar_config(jugadores, comportamiento)

    config.starting_players[0].behavior_id = 9999
    with pytest.raises(InvalidConfigurationError):
        validate_lineup(session, config, jugadores)


def test_deberia_guardar_3_titulares_con_rol_y_3_suplentes_sin_rol(session, local, partido, comportamiento):
    jugadores = crear_jugadores(session, local)
    config = armar_config(jugadores, comportamiento)

    save_lineup(session, partido.match_id, local.team_id, config)
    session.commit()  # save_lineup necesita q yo haga el commit

    entradas = session.scalars(
        select(LineupEntry).where(LineupEntry.match_id == partido.match_id)
    ).all()
    assert len(entradas) == 6

    titulares = 0
    suplentes = 0
    for entrada in entradas:
        if entrada.is_starter:
            titulares += 1
            assert entrada.role is not None 
        else:
            suplentes += 1
            assert entrada.role is None      
    assert titulares == 3
    assert suplentes == 3


def test_deberia_no_guardar_nada_si_no_se_hace_commit(session, local, partido, comportamiento):
    jugadores = crear_jugadores(session, local)
    config = armar_config(jugadores, comportamiento)
    id_partido = partido.match_id

    save_lineup(session, id_partido, local.team_id, config)
    session.rollback()  # deshago sin haber hecho commit

    # si save_lineup hubiera hecho commit, aca habrian 6 entradas
    entradas = session.scalars(select(LineupEntry).where(LineupEntry.match_id == id_partido)).all()
    assert len(entradas) == 0