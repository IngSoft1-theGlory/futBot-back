"""
Tests simples del modelo Match.

Cada test arma sus propios datos a la vista, sin ayudas escondidas.
Se leen de arriba hacia abajo: primero lo que tiene que funcionar,
despues lo que la base tiene que rechazar.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.models import Team
from src.models.match import Match, MatchStatus


# Equipos para usar en los tests 
@pytest.fixture()
def local(session):
    equipo = Team(team_name="Local FC")
    session.add(equipo)
    session.commit()
    return equipo


@pytest.fixture()
def visitante(session):
    equipo = Team(team_name="Visitante FC")
    session.add(equipo)
    session.commit()
    return equipo


def test_deberia_asignar_id_y_valores_por_defecto_al_crear_un_partido(session, local):
    # Crea un partido pasando solo lo obligatorio, anfitrion y duracion.
    partido = Match(team_host_id=local.team_id, match_duration=10)
    session.add(partido)
    session.commit()

    # chequea que la base le puso el id, el estado inicial, los goles en 0 y la fecha.
    assert partido.match_id is not None
    assert partido.status == MatchStatus.PENDING
    assert partido.home_goals == 0
    assert partido.away_goals == 0
    assert partido.created_at is not None


def test_deberia_asignar_ids_distintos_a_dos_partidos_del_mismo_equipo(session, local):
    # Tambien prueba que un mismo equipo puede tener varios partidos a la vez.
    p1 = Match(team_host_id=local.team_id, match_duration=10)
    p2 = Match(team_host_id=local.team_id, match_duration=10)
    session.add_all([p1, p2])
    session.commit()

    assert p1.match_id != p2.match_id


def test_deberia_permitir_partido_pending_sin_visitante(session, local):
    # PENDING = el anfitrion espera rival, todavia no hay visitante.
    partido = Match(team_host_id=local.team_id, match_duration=10)
    session.add(partido)
    session.commit()

    assert partido.team_away_id is None
    assert partido.away_team is None
    assert partido.host_team.team_id == local.team_id


def test_deberia_guardar_equipos_y_resultado_de_un_partido_terminado(session, local, visitante):
    # chequea que un partido terminado tiene ambos equipos y el resultado final.
    partido = Match(
        team_host_id=local.team_id,
        team_away_id=visitante.team_id,
        match_duration=10,
        status=MatchStatus.FINISHED,
        home_goals=3,
        away_goals=1,
    )
    session.add(partido)
    session.commit()

    # expire_all fuerza a releer desde la base, no desde la memoria.
    session.expire_all()
    guardado = session.get(Match, partido.match_id)

    assert guardado.host_team.team_id == local.team_id
    assert guardado.away_team.team_id == visitante.team_id
    assert guardado.status == MatchStatus.FINISHED
    assert (guardado.home_goals, guardado.away_goals) == (3, 1)


def test_deberia_fallar_partido_en_progreso_sin_visitante(session, local):
    # Solo un partido PENDING puede no tener visitante.
    partido = Match(
        team_host_id=local.team_id,
        match_duration=10,
        status=MatchStatus.IN_PROGRESS,
    )
    session.add(partido)
    with pytest.raises(IntegrityError):
        session.commit()


def test_deberia_fallar_si_el_equipo_juega_contra_si_mismo(session, local):
    partido = Match(
        team_host_id=local.team_id,
        team_away_id=local.team_id,  # mismo equipo de los dos lados
        match_duration=10,
        status=MatchStatus.IN_PROGRESS,
    )
    session.add(partido)
    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize("duracion", [0, -5])
def test_deberia_fallar_si_la_duracion_es_cero_o_negativa(session, local, duracion):
    # Este test corre dos veces: una con 0 y otra con -5.
    partido = Match(team_host_id=local.team_id, match_duration=duracion)
    session.add(partido)
    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize("campo", ["home_goals", "away_goals"])
def test_deberia_fallar_si_los_goles_son_negativos(session, local, campo):
    # Corre dos veces: una con goles negativos del anfitrion y otra del visitante.
    partido = Match(team_host_id=local.team_id, match_duration=10, **{campo: -1})
    session.add(partido)
    with pytest.raises(IntegrityError):
        session.commit()


def test_deberia_borrar_el_partido_al_borrar_el_equipo_anfitrion(session, local):
    partido = Match(team_host_id=local.team_id, match_duration=10)
    session.add(partido)
    session.commit()
    id_partido = partido.match_id

    session.delete(local)
    session.commit()
    session.expire_all()

    # chequea que ya no existe porque la base lo borro por el ondelete="CASCADE".
    assert session.get(Match, id_partido) is None


def test_deberia_borrar_el_partido_al_borrar_el_equipo_visitante(session, local, visitante):
    # Mismo caso pero borrando al visitante (prueba la FK de team_away_id)
    partido = Match(
        team_host_id=local.team_id,
        team_away_id=visitante.team_id,
        match_duration=10,
        status=MatchStatus.IN_PROGRESS,
    )
    session.add(partido)
    session.commit()
    id_partido = partido.match_id

    session.delete(visitante)
    session.commit()
    session.expire_all()

    assert session.get(Match, id_partido) is None