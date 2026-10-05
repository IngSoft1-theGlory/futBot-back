"""
Tests del modelo LineupEntry (configuracion tactica de un equipo en un partido)
"""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.models import Behavior, LineupEntry, Match, MatchStatus, Player, Team


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
        match_duration=10,
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


def entry(partido, equipo, jugador, comportamiento, role=None, is_starter=False):
    """Arma una LineupEntry (sin guardarla). Por defecto es suplente sin rol."""
    return LineupEntry(
        match_id=partido.match_id,
        team_id=equipo.team_id,
        player_id=jugador.player_id,
        behavior_id=comportamiento.behavior_id,
        role=role,
        is_starter=is_starter,
    )


def test_deberia_guardar_titular_con_rol_y_suplente_sin_rol(session, partido, local, comportamiento):
    # Desempaqueta la lista de 2 jugadores en dos variables.
    titular, suplente = crear_jugadores(session, local, cantidad=2)

    session.add(entry(partido, local, titular, comportamiento, role="FORWARD", is_starter=True))
    session.add(entry(partido, local, suplente, comportamiento))
    session.commit()
    session.expire_all()  # obliga a releer desde la base, no desde la memoria

    guardadas = session.scalars(select(LineupEntry)).all()
    assert len(guardadas) == 2
    # El titular guardo su rol y el suplente quedo con None (NULL en la base).
    assert {e.role for e in guardadas} == {"FORWARD", None}


def test_deberia_permitir_al_mismo_jugador_estar_en_partidos_distintos(
    session, partido, local, visitante, comportamiento
):
    # Segundo partido entre los mismos equipos.
    otro_partido = Match(
        team_host_id=local.team_id,
        team_away_id=visitante.team_id,
        match_duration=10,
        status=MatchStatus.IN_PROGRESS,
    )
    session.add(otro_partido)
    session.commit()
    jugador = crear_jugadores(session, local, cantidad=1)[0]  # [0]: saca al jugador en la posicion 0 de la lista

    # El mismo jugador, una vez en cada partido.
    session.add(entry(partido, local, jugador, comportamiento))
    session.add(entry(otro_partido, local, jugador, comportamiento))
    session.commit()  # no tiene que fallar

    assert len(session.scalars(select(LineupEntry)).all()) == 2


def test_deberia_fallar_si_un_titular_no_tiene_rol(session, partido, local, comportamiento):
    jugador = crear_jugadores(session, local, cantidad=1)[0]
    session.add(entry(partido, local, jugador, comportamiento, role=None, is_starter=True))
    with pytest.raises(IntegrityError):
        session.commit()


def test_deberia_fallar_si_un_suplente_tiene_rol(session, partido, local, comportamiento):
    jugador = crear_jugadores(session, local, cantidad=1)[0]
    session.add(entry(partido, local, jugador, comportamiento, role="FORWARD", is_starter=False))
    with pytest.raises(IntegrityError):
        session.commit()


def test_deberia_fallar_si_el_rol_no_es_valido(session, partido, local, comportamiento):
    jugador = crear_jugadores(session, local, cantidad=1)[0]
    session.add(entry(partido, local, jugador, comportamiento, role="ARQUERO", is_starter=True))
    with pytest.raises(IntegrityError):
        session.commit()


def test_deberia_fallar_si_el_jugador_se_repite_en_el_mismo_partido(
    session, partido, local, comportamiento
):
    jugador = crear_jugadores(session, local, cantidad=1)[0]
    session.add(entry(partido, local, jugador, comportamiento))
    session.add(entry(partido, local, jugador, comportamiento))  # mismo jugador otra vez
    with pytest.raises(IntegrityError):
        session.commit()


def test_deberia_fallar_si_el_rol_se_repite_en_el_mismo_equipo_y_partido(
    session, partido, local, comportamiento
):
    j1, j2 = crear_jugadores(session, local, cantidad=2)
    # Dos jugadores distintos con el mismo rol en el mismo equipo y partido.
    session.add(entry(partido, local, j1, comportamiento, role="FORWARD", is_starter=True))
    session.add(entry(partido, local, j2, comportamiento, role="FORWARD", is_starter=True))
    with pytest.raises(IntegrityError):
        session.commit()


def test_deberia_fallar_si_el_jugador_no_existe(session, partido, local, comportamiento):
    inexistente = Player(player_id=9999)  # solo nos interesa su id, no se guarda en la base
    session.add(entry(partido, local, inexistente, comportamiento))
    with pytest.raises(IntegrityError):
        session.commit()


def test_deberia_fallar_si_el_comportamiento_no_existe(session, partido, local):
    jugador = crear_jugadores(session, local, cantidad=1)[0]
    inexistente = Behavior(behavior_id=9999)  # solo nos interesa su id, no se guarda en la base
    session.add(entry(partido, local, jugador, inexistente))
    with pytest.raises(IntegrityError):
        session.commit()


def _guardar_una_entry(session, partido, equipo, comportamiento):
    # Ayuda para los tests de borrado que guarda una entry y devuelve su id y su jugador.
    jugador = crear_jugadores(session, equipo, cantidad=1)[0]
    e = entry(partido, equipo, jugador, comportamiento)
    session.add(e)
    session.commit()
    return e.entry_id, jugador


def test_deberia_borrar_las_entries_al_borrar_el_partido(session, partido, local, comportamiento):
    entry_id, _ = _guardar_una_entry(session, partido, local, comportamiento)

    session.delete(partido)
    session.commit()
    session.expire_all()

    # Ya no existe, la base la borro por el ondelete="CASCADE" de match_id
    assert session.get(LineupEntry, entry_id) is None


def test_deberia_borrar_las_entries_al_borrar_el_jugador(session, partido, local, comportamiento):
    entry_id, jugador = _guardar_una_entry(session, partido, local, comportamiento)

    session.delete(jugador)
    session.commit()
    session.expire_all()

    assert session.get(LineupEntry, entry_id) is None

def test_deberia_borrar_las_entries_al_borrar_el_equipo(session, partido, local, comportamiento):
    entry_id, _ = _guardar_una_entry(session, partido, local, comportamiento)

    session.delete(local)
    session.commit()
    session.expire_all()

    # Ya no existe: la base la borró al borrar el equipo.
    assert session.get(LineupEntry, entry_id) is None