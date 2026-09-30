"""
Tests del modelo Player: persistencia y constraints a nivel de base de
datos.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from src.models.player import Player
from src.models.team import Team


def _datos_jugador_valido(team_id: int, number: int = 10) -> dict:
    """Payload base con atributos PACSS válidos (suma = 300)."""
    return {
        "team_id": team_id,
        "name": "Lionel Messi",
        "number": number,
        "power": 60,
        "agility": 60,
        "control": 60,
        "speed": 60,
        "strength": 60,
    }


def test_guardar_jugador_valido_y_recuperarlo_por_id(session, usuario_con_equipo):
    """Un jugador válido se persiste y se puede recuperar por player_id."""
    jugador = Player(**_datos_jugador_valido(usuario_con_equipo.team_id))

    session.add(jugador)
    session.commit()

    recuperado = session.get(Player, jugador.player_id)

    assert recuperado is not None
    assert recuperado.name == "Lionel Messi"
    assert recuperado.team_id == usuario_con_equipo.team_id


def test_listar_jugadores_de_un_equipo_no_trae_los_de_otro(session, usuario_con_equipo):
    """El listado filtrado por team_id no debe traer jugadores de otro equipo."""
    otro_equipo = Team(team_name="Equipo Rival")
    session.add(otro_equipo)
    session.flush()  # para tener otro_equipo.team_id sin hacer commit todav
    session.add(Player(**_datos_jugador_valido(usuario_con_equipo.team_id, number=9)))
    session.add(Player(**_datos_jugador_valido(usuario_con_equipo.team_id, number=10)))
    session.add(Player(**_datos_jugador_valido(otro_equipo.team_id, number=9)))
    session.commit()

    jugadores_del_equipo = (
        session.query(Player)
        .filter(Player.team_id == usuario_con_equipo.team_id)
        .all()
    )

    assert len(jugadores_del_equipo) == 2
    assert all(j.team_id == usuario_con_equipo.team_id for j in jugadores_del_equipo)


def test_falta_name_lanza_integrity_error(session, usuario_con_equipo):
    """name es NOT NULL: omitirlo debe fallar a nivel de base de datos."""
    datos = _datos_jugador_valido(usuario_con_equipo.team_id)
    datos["name"] = None

    session.add(Player(**datos))

    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()


def test_team_id_nulo_lanza_integrity_error(session):
    """team_id es NOT NULL: no puede existir un jugador sin equipo."""
    datos = _datos_jugador_valido(team_id=None)

    session.add(Player(**datos))

    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()


def test_numero_repetido_en_mismo_equipo_lanza_integrity_error(session, usuario_con_equipo):
    """La UniqueConstraint(team_id, number) rechaza dos jugadores con el mismo number en el mismo equipo."""
    session.add(Player(**_datos_jugador_valido(usuario_con_equipo.team_id, number=10)))
    session.commit()
    session.add(Player(**_datos_jugador_valido(usuario_con_equipo.team_id, number=10)))

    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()


def test_mismo_numero_en_equipos_distintos_es_valido(session, usuario_con_equipo):
    """El mismo number SÍ debe poder repetirse si es en equipos distintos (constraint compuesta, no global)."""
    otro_equipo = Team(team_name="Equipo Rival")
    session.add(otro_equipo)
    session.flush()

    session.add(Player(**_datos_jugador_valido(usuario_con_equipo.team_id, number=10)))
    session.add(Player(**_datos_jugador_valido(otro_equipo.team_id, number=10)))

    session.commit()  # no debe lanzar ninguna excepción


def test_borrar_equipo_elimina_sus_jugadores_por_cascada(session):
    """cascade='all, delete-orphan' en Team.player: al borrar el equipo, sus jugadores no quedan huérfanos."""
    equipo = Team(team_name="Equipo Descartable")
    session.add(equipo)
    session.flush()

    jugador = Player(**_datos_jugador_valido(equipo.team_id))
    session.add(jugador)
    session.commit()
    jugador_id = jugador.player_id

    session.delete(equipo)
    session.commit()

    assert session.get(Player, jugador_id) is None