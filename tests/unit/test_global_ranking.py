"""Tests del ranking global"""

from src.routes.rankings import get_global_ranking_endpoint
from tests.unit.test_list_leagues_endpoint import _crear_equipo


def _equipo_con_stats(session, nombre, points=0, goals_for=0, goals_against=0):
    equipo = _crear_equipo(session, nombre)
    equipo.points = points
    equipo.goals_for = goals_for
    equipo.goals_against = goals_against
    session.commit()
    return equipo


def _ranking(session, page=None, limit=None):
    return get_global_ranking_endpoint(page=page, limit=limit, user_id=1, session=session)


def test_deberia_ordenar_por_puntos_y_ante_empate_por_diferencia_de_goles(session):
    # los creo desordenados para ver si los ordena
    c = _equipo_con_stats(session, "C", points=3, goals_for=1, goals_against=0)  # 3 pts, dif +1
    b = _equipo_con_stats(session, "B", points=6, goals_for=2, goals_against=2)  # 6 pts, dif 0
    a = _equipo_con_stats(session, "A", points=6, goals_for=5, goals_against=1)  # 6 pts, dif +4

    respuesta = _ranking(session)
    
    # ids de los equipos, en el orden en que quedaron en el ranking
    ids_en_el_ranking = []
    for fila in respuesta.ranking:
        ids_en_el_ranking.append(fila.team_id)

    # el orden esperado: A (6 pts, dif +4), B (6 pts, dif 0), C (3 pts)
    orden_esperado = [a.team_id, b.team_id, c.team_id]

    assert ids_en_el_ranking == orden_esperado
    

def test_deberia_incluir_a_los_clubes_sin_partidos_jugados(session):
    con_puntos = _equipo_con_stats(session, "ConPuntos", points=3, goals_for=1)
    sin_partidos = _equipo_con_stats(session, "SinPartidos")  # todo en 0

    respuesta = _ranking(session)

    # tiene que aparecer, y ultimo porque no tiene puntos
    ids_en_el_ranking = []
    for fila in respuesta.ranking:
        ids_en_el_ranking.append(fila.team_id)
    assert ids_en_el_ranking == [con_puntos.team_id, sin_partidos.team_id]

    # y con sus estadisticas en 0
    ultima_fila = respuesta.ranking[1]
    assert ultima_fila.matches_played == 0
    assert ultima_fila.points == 0
    assert ultima_fila.goal_diff == 0


def test_deberia_calcular_la_posicion_sobre_el_ranking_completo_en_la_segunda_pagina(session):
    # 5 equipos con puntos 50, 40, 30, 20, 10 (puestos 1 al 5), creados en desorden
    e3 = _equipo_con_stats(session, "E3", points=30)
    e5 = _equipo_con_stats(session, "E5", points=10)
    e1 = _equipo_con_stats(session, "E1", points=50)
    e4 = _equipo_con_stats(session, "E4", points=20)
    e2 = _equipo_con_stats(session, "E2", points=40)

    # muestro de a 2 por pagina. la pagina 2 deberia tener los puestos 3 y 4
    respuesta = _ranking(session, page="2", limit="2")

    posiciones = []
    ids_en_el_ranking = []
    for fila in respuesta.ranking:
        posiciones.append(fila.position)
        ids_en_el_ranking.append(fila.team_id)

    assert posiciones == [3, 4]
    assert ids_en_el_ranking == [e3.team_id, e4.team_id]  # chequeo que en la pagina 2 estan los puestos 3 y 4
    assert respuesta.pagination.total_pages == 3  # chequeo que son 3 paginas 


def test_deberia_devolver_lista_vacia_si_no_hay_clubes(session):
    respuesta = _ranking(session)  # no se creo ningun equipo

    assert respuesta.ranking == []
    assert respuesta.pagination.total_items == 0
    assert respuesta.pagination.total_pages == 0