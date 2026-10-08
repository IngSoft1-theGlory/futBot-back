"""
Tests de los criterios de aceptacion del modelo de ligas.
"""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from src.models.behavior import Behavior
from src.models.league import League, LeagueStatus
from src.models.lineup_entry import LineupEntry
from src.models.match import Match
from src.models.player import Player


# Un fixture crea algo antes del test y se lo pasa por parametro.
# Cada uno de estos guarda un objeto en la base y lo devuelve.

@pytest.fixture()
def liga(session, usuario_con_equipo):
    liga = League(league_name="Copa", max_teams=8, match_duration=2,
                  host_team_id=usuario_con_equipo.team.team_id)
    session.add(liga)      # lo marca para guardar
    session.commit()       # lo escribe en la base (aca se aplican los CHECK y UNIQUE)
    return liga


@pytest.fixture()
def jugador(session, usuario_con_equipo):
    # Player exige las 5 stats, pero para estos tests no importan
    jugador = Player(team_id=usuario_con_equipo.team.team_id, name="Jugador 1", number=1,
                     power=1, agility=1, control=1, speed=1, strength=1)
    session.add(jugador)
    session.commit()
    return jugador


@pytest.fixture()
def otro_jugador(session, usuario_con_equipo):
    otro = Player(team_id=usuario_con_equipo.team.team_id, name="Jugador 2", number=2,
                  power=1, agility=1, control=1, speed=1, strength=1)
    session.add(otro)
    session.commit()
    return otro


@pytest.fixture()
def comportamiento(session):
    # lineup_entries necesita un behavior_id valido (es una FK obligatoria)
    comportamiento = Behavior(name="Neutro", description="Prueba", code="pass")
    session.add(comportamiento)
    session.commit()
    return comportamiento


# Una liga valida se guarda en la base y se puede leer 

def test_deberia_persistir_liga_con_sus_datos(session, usuario_con_equipo):
    nueva = League(
        league_name="TheParrilleros",
        max_teams=8,
        match_duration=5,
        host_team_id=usuario_con_equipo.team.team_id,
    )
    session.add(nueva)
    session.commit()
    # Despues del commit los atributos se vuelven a leer de la base al usarlos
    # asi que estos asserts comprueban lo que realmente quedo guardado

    assert nueva.league_id is not None            # la base le asigno un id
    assert nueva.league_name == "TheParrilleros"
    assert nueva.host_team_id == usuario_con_equipo.team.team_id
    assert nueva.status == LeagueStatus.PENDING   # valor por defecto debe ser pending


# La liga acepta o rechaza el cupo y la duracion 

def test_deberia_aceptar_cupo_par_entre_4_y_12(session, usuario_con_equipo):
    host_id = usuario_con_equipo.team.team_id
    session.add(League(league_name="A", max_teams=4, match_duration=2, host_team_id=host_id))
    session.add(League(league_name="B", max_teams=12, match_duration=2, host_team_id=host_id))
    session.commit()   # si rechazara 4 o 12, esto lanzaria IntegrityError y el test fallaria


def test_deberia_rechazar_cupo_menor_a_4(session, usuario_con_equipo):
    session.add(League(league_name="TheParrilleros", max_teams=2, match_duration=2,
                       host_team_id=usuario_con_equipo.team.team_id))
    # El test pasa solo si el commit falla con IntegrityError
    with pytest.raises(IntegrityError):
        session.commit()


def test_deberia_rechazar_duracion_cero(session, usuario_con_equipo):
    session.add(League(league_name="TheParrilleros", max_teams=8, match_duration=0,
                       host_team_id=usuario_con_equipo.team.team_id))
    with pytest.raises(IntegrityError):
        session.commit()


# Una fila de lineup_entries es de un partido o de una liga

def test_deberia_rechazar_alineacion_sin_partido_ni_liga(
    session, usuario_con_equipo, jugador, comportamiento
):
    # tanto match_id como league_id quedan en null
    fila = LineupEntry(
        team_id=usuario_con_equipo.team.team_id,
        player_id=jugador.player_id,
        behavior_id=comportamiento.behavior_id,
        role="FORWARD",
        is_starter=True,
    )
    session.add(fila)
    with pytest.raises(IntegrityError):
        session.commit()


def test_deberia_rechazar_alineacion_con_partido_y_liga_a_la_vez(
    session, usuario_con_equipo, liga, jugador, comportamiento
):
    partido = Match(match_duration=2, team_host_id=usuario_con_equipo.team.team_id)
    session.add(partido)
    session.commit()

    # le paso tanto match_id como league_id para ver que lo rechace
    fila = LineupEntry(
        match_id=partido.match_id,  
        league_id=liga.league_id,
        team_id=usuario_con_equipo.team.team_id,
        player_id=jugador.player_id,
        behavior_id=comportamiento.behavior_id,
        role="FORWARD",
        is_starter=True,
    )
    session.add(fila)
    with pytest.raises(IntegrityError):
        session.commit()


# No se repite jugador dentro de una liga 
def test_deberia_rechazar_mismo_jugador_dos_veces_en_la_liga(
    session, usuario_con_equipo, liga, jugador, comportamiento
):
    fila_1 = LineupEntry(
        league_id=liga.league_id,
        team_id=usuario_con_equipo.team.team_id,
        player_id=jugador.player_id,
        behavior_id=comportamiento.behavior_id,
        role="FORWARD",
        is_starter=True,
    )
    fila_2 = LineupEntry(
        league_id=liga.league_id,
        team_id=usuario_con_equipo.team.team_id,
        player_id=jugador.player_id,        # mismo jugador
        behavior_id=comportamiento.behavior_id,
        role="DEFENDER",                    
        is_starter=True,
    )
    session.add_all([fila_1, fila_2])       # guarda las dos juntas
    with pytest.raises(IntegrityError):
        session.commit()