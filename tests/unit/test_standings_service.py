"""
Tests de build_standings: estadísticas de cada equipo y orden de la tabla
"""

import pytest

from src.models import Match, MatchStatus, Team
from src.services.standings_service import build_standings


def _equipos(*ids):
    """ Crea una lista de equipos con los ids y nombres dados"""
    return [Team(team_id=i, team_name=f"Equipo {i}") for i in ids]


def _partido(local, visitante, goles_local, goles_visitante):
    """ Crea un partido terminado entre los equipos dados, con los goles dados"""
    return Match(
        team_host_id=local, team_away_id=visitante,
        home_goals=goles_local, away_goals=goles_visitante,
        status=MatchStatus.FINISHED,
    )


def _orden(tabla):
    """ Devuelve la lista de team_id en el orden de la tabla, que es el orden de posición"""
    return [fila.team_id for fila in tabla]


def test_deberia_arrancar_todos_en_cero_sin_partidos_terminados():
    # Se obtiene la tabla con los equipos en orden de team_id, no de posición
    tabla = build_standings(_equipos(3, 1, 2), [])

    # La tabla debería estar ordenada por team_id, y las posiciones deberían ser 1..N
    assert _orden(tabla) == [1, 2, 3]
    assert [fila.position for fila in tabla] == [1, 2, 3]
    for fila in tabla:
        assert (fila.matches_played, fila.wins, fila.draws, fila.losses) == (0, 0, 0, 0)
        assert (fila.goals_for, fila.goals_against, fila.goal_diff, fila.points) == (0, 0, 0, 0)


def test_deberia_calcular_las_estadisticas_de_cada_equipo():
    # Partidos: 1 gana a 2 por 3-1, y luego empatan 2-2
    partidos = [_partido(1, 2, 3, 1), _partido(2, 1, 2, 2)]

    # se obtiene la tabla con los equipos en orden de team_id, no de posición
    tabla = build_standings(_equipos(1, 2), partidos)
    # primero y segundo son los equipos en orden de posición, no de team_id
    primero, segundo = tabla

    # Estadísticas del primero y segundo
    assert primero.team_id == 1
    assert (primero.matches_played, primero.wins, primero.draws, primero.losses) == (2, 1, 1, 0)
    assert (primero.goals_for, primero.goals_against, primero.goal_diff, primero.points) == (5, 3, 2, 4)
    assert segundo.team_id == 2
    assert (segundo.matches_played, segundo.wins, segundo.draws, segundo.losses) == (2, 0, 1, 1)
    assert (segundo.goals_for, segundo.goals_against, segundo.goal_diff, segundo.points) == (3, 5, -2, 1)


# Orden, un caso por criterio
# (En cada uno, los criterios anteriores empatan)
@pytest.mark.parametrize(
    "partidos, esperado",
    [
        # puntos: gana el 2, que tendría que quedar primero aunque su id sea mayor
        ([_partido(2, 1, 1, 0)], [2, 3, 4, 1]),
        # diferencia de gol: 1 y 2 tienen 3 puntos, pero 2 tiene +3 y 1 tiene +1
        ([_partido(1, 3, 1, 0), _partido(2, 4, 3, 0)], [2, 1, 3, 4]),
        # goles a favor: 1 y 2 tienen 3 puntos y +1, pero 2 convirtió más
        ([_partido(1, 3, 1, 0), _partido(2, 4, 2, 1)], [2, 1, 4, 3]),
    ],
    ids=["puntos", "diferencia_de_gol", "goles_a_favor"],
)

def test_deberia_ordenar_la_tabla_segun_los_criterios(partidos, esperado):
    tabla = build_standings(_equipos(1, 2, 3, 4), partidos)

    # La tabla debería estar ordenada según el criterio de desempate, 
    # y las posiciones deberían ser 1..N
    assert _orden(tabla) == esperado
    assert [fila.position for fila in tabla] == list(range(1, len(esperado) + 1))