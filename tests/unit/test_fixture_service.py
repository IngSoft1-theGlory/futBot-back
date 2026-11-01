"""Tests de generate_fixture: cantidad de partidos, fechas y datos de cada partido."""

import pytest
from sqlalchemy import select

from src.models import Behavior, League, LineupEntry, Match, MatchStatus, Player, Team
from src.services.fixture_service import generate_fixture


def _liga_con_equipos(session, cantidad, match_duration=5):
    """
    Liga PENDING con cantidad equipos inscriptos (una fila de lineup_entries por equipo alcanza)
    """
    # Se crean los equipos, un comportamiento y la liga
    equipos = [Team(team_name=f"Equipo {i}") for i in range(cantidad)]
    session.add_all(equipos)
    comportamiento = Behavior(name="Patear", description="x", code="def on_tick(api): pass", is_default=True)
    session.add(comportamiento)
    session.commit()

    # Se crea la liga con el primer equipo como host, y se agregan los jugadores y lineup_entries de cada equipo
    liga = League(
        league_name="Liga", max_teams=12, match_duration=match_duration,
        host_team_id=equipos[0].team_id,
    )
    session.add(liga)
    session.commit()

    # Se agregan jugadores y lineup_entries para cada equipo
    for equipo in equipos:
        jugador = Player(
            team_id=equipo.team_id, name="J", number=1,
            power=60, agility=60, control=60, speed=60, strength=60,
        )
        session.add(jugador)
        session.flush()
        session.add(LineupEntry(
            league_id=liga.league_id, team_id=equipo.team_id, player_id=jugador.player_id,
            behavior_id=comportamiento.behavior_id, role=None, is_starter=False,
        ))
    session.commit()
    return liga


def _partidos_de(session, liga):
    # Devuelve la lista de partidos de la liga, sin importar el orden
    return list(session.scalars(select(Match).where(Match.league_id == liga.league_id)).all())


# primer criterio: todos contra todos, N equipos, N-1 fechas, cada equipo juega una sola vez por fecha
@pytest.mark.parametrize("cantidad", [4, 6, 8, 10, 12])
def test_deberia_crear_todos_contra_todos_en_n_menos_1_fechas(session, cantidad):
    liga = _liga_con_equipos(session, cantidad)

    # Genera y guarda los partidos de la liga
    generate_fixture(session, liga)
    session.commit()
    # Obtiene los partidos guardados para comprobar el resultado
    partidos = _partidos_de(session, liga)

    # Cada equipo debe enfrentarse una vez contra todos los demás
    assert len(partidos) == cantidad * (cantidad - 1) // 2

    # Agrupa los partidos según la fecha a la que pertenecen
    fechas = {}
    for p in partidos:
        fechas.setdefault(p.round_number, []).append(p)
    # Con N equipos deben existir N-1 fechas, numeradas desde 1
    assert set(fechas) == set(range(1, cantidad))

    # en cada fecha, cada equipo juega una sola vez
    for partidos_de_fecha in fechas.values():
        equipos = [e for p in partidos_de_fecha for e in (p.team_host_id, p.team_away_id)]
        assert len(equipos) == cantidad
        assert len(set(equipos)) == cantidad

    # cada par de equipos se enfrenta una sola vez
    pares = {frozenset((p.team_host_id, p.team_away_id)) for p in partidos}
    assert len(pares) == len(partidos)


# segundo criterio: los partidos pertenecen a la liga, con su duración, PENDING y número de fecha
def test_deberia_guardar_los_partidos_con_los_datos_de_la_liga(session):
    # Se crea una liga con 4 equipos y duración de partido de 2
    liga = _liga_con_equipos(session, 4, match_duration=2)

    # Se generan los partidos
    generate_fixture(session, liga)
    session.commit()

    # cada partido tiene los datos de la liga
    for partido in _partidos_de(session, liga):
        assert partido.league_id == liga.league_id
        assert partido.match_duration == 2
        assert partido.status == MatchStatus.PENDING
        assert partido.round_number is not None