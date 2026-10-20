"""
Tests unitarios del endpoint PUT /api/v1/leagues/{league_id} (iniciar liga)

Se prueba los tests unitarios (criterios de aceptacion):
    - CA1 : se deberia iniciar la liga y guardar el fixture de partidos 
        y publicar un evento LEAGUE_INITIATED
    - CA2 : no deberia cambiar nada si el put falla (liga no cambia, no hay fixture, no hay eventos)
    - CA3 : deberia iniciar la liga sola y publicar los dos eventos si el equipo completa el cupo
    - CA4 : deberia seguir pending si el equipo no completa el cupo
"""

import pytest
from sqlalchemy import func, select

from src.models import League, LeagueStatus, LineupEntry, Match
from src.realtime.event_bus import event_bus

# Se reutilizan helpers y fixtures de otros archivos de tests
from tests.unit.test_join_league_service import armar_body, crear_jugadores, crear_liga, crear_usuario
from tests.unit.test_post_friendly_endpoint import client, comportamiento, db, headers

URL = "/api/v1/leagues"


# --- Helpers ---

@pytest.fixture()
def cola_de_eventos():
    """Se suscribe al bus para capturar los eventos publicados durante el test."""
    queue = event_bus.subscribe()
    yield queue
    # Evita que la suscripcion afecte a otros tests
    event_bus.unsubscribe(queue)


def leer_eventos(queue):
    """Devuelve todos los eventos publicados en la cola y la vacia."""
    return [queue.get_nowait() for _ in range(queue.qsize())]


def crear_liga_con_equipos(db, cantidad, status=LeagueStatus.PENDING, max_teams=12):
    """
    Liga con `cantidad` equipos inscriptos (el anfitrion + los demas).
    Devuelve (anfitrion, otros_usuarios, liga).
    """
    anfitrion = crear_usuario(db, "host")
    liga = crear_liga(db, anfitrion, max_teams=max_teams, status=status)
    otros = []
    for n in range(cantidad - 1):
        otro = crear_usuario(db, f"otro{n}")
        for jugador in crear_jugadores(db, otro.team_id):
            db.add(LineupEntry(
                league_id=liga.league_id, team_id=otro.team_id, player_id=jugador.player_id,
                behavior_id=1, role=None, is_starter=False,
            ))
        otros.append(otro)
    db.commit()
    return anfitrion, otros, liga


def contar_partidos(db, league_id):
    """Devuelve la cantidad de partidos guardados en la liga."""
    return db.scalar(select(func.count()).select_from(Match).where(Match.league_id == league_id))


def estado_de(db, league_id):
    db.expire_all()  # evita leer un valor viejo guardado en la sesion del test
    return db.get(League, league_id).status


# ---- caso exitoso ----
def test_deberia_iniciar_la_liga_guardar_el_fixture_y_publicar_un_solo_evento(
    client, db, comportamiento, cola_de_eventos
):
    anfitrion, _, liga = crear_liga_con_equipos(db, 4, max_teams=4)
    league_id = liga.league_id

    # el anfitrion solicita iniciar la liga mediante el endpoint PUT,
    # autenticandose como el usuario que la creo.
    r = client.put(f"{URL}/{league_id}", json={"status": "IN_PROGRESS"}, headers=headers(anfitrion))

    assert r.status_code == 200
    assert r.json() == {"league_id": league_id, "league_name": "Liga test", "status": "IN_PROGRESS"}
    assert estado_de(db, league_id) == LeagueStatus.IN_PROGRESS
    assert contar_partidos(db, league_id) == 6  # 4 equipos: 4*3/2 partidos
    assert leer_eventos(cola_de_eventos) == [{
        "event": "LEAGUE_INITIATED",
        "data": {"league_id": league_id, "league_name": "Liga test", "max_teams": 4, "status": "IN_PROGRESS"},
    }]


# --- errores (la liga no cambia, no hay fixture, no hay eventos) ---

# (equipos, estado inicial, quien llama, id de liga, body, codigo HTTP, error)
CASOS_DE_ERROR = [
    pytest.param(4, LeagueStatus.PENDING, "nadie", None, {"status": "IN_PROGRESS"},
                 401, "UNAUTHORIZED", id="sin_token"),
    pytest.param(4, LeagueStatus.PENDING, "otro", None, {"status": "IN_PROGRESS"},
                 403, "UNAUTHORIZED_ACTION", id="no_es_anfitrion"),
    pytest.param(4, LeagueStatus.PENDING, "anfitrion", 9999, {"status": "IN_PROGRESS"},
                 404, "LEAGUE_NOT_FOUND", id="liga_inexistente"),
    pytest.param(4, LeagueStatus.IN_PROGRESS, "anfitrion", None, {"status": "IN_PROGRESS"},
                 409, "LEAGUE_ALREADY_STARTED", id="liga_ya_iniciada"),
    pytest.param(2, LeagueStatus.PENDING, "anfitrion", None, {"status": "IN_PROGRESS"},
                 400, "INSUFFICIENT_TEAMS", id="menos_de_4_equipos"),
    pytest.param(5, LeagueStatus.PENDING, "anfitrion", None, {"status": "IN_PROGRESS"},
                 400, "ODD_TEAMS_COUNT", id="cantidad_impar"),
    pytest.param(4, LeagueStatus.PENDING, "anfitrion", None, {"status": "FINISHED"},
                 422, "VALIDATION_ERROR", id="status_invalido"),
]


@pytest.mark.parametrize("equipos, estado, quien, id_liga, body, codigo, error", CASOS_DE_ERROR)
def test_no_deberia_cambiar_nada_si_el_put_falla(
    client, db, comportamiento, cola_de_eventos, equipos, estado, quien, id_liga, body, codigo, error
):
    anfitrion, otros, liga = crear_liga_con_equipos(db, equipos, status=estado)
    league_id = liga.league_id
    # Se arma un diccionario de headers para cada usuario (anfitrion, otro, nadie)
    headers_de = {"anfitrion": headers(anfitrion), "otro": headers(otros[0]) if otros else {}, "nadie": {}}

    # el usuario solicita iniciar la liga mediante el endpoint PUT,
    # autenticandose como el usuario que la creo.
    r = client.put(f"{URL}/{id_liga or league_id}", json=body, headers=headers_de[quien])

    assert r.status_code == codigo
    assert r.json()["error"] == error
    assert estado_de(db, league_id) == estado   # la liga no cambia
    assert contar_partidos(db, league_id) == 0  # no se crea el fixture
    assert leer_eventos(cola_de_eventos) == []  # no se publica ningun evento


# --- Inicio automatico al completar el cupo ---

def test_deberia_iniciar_la_liga_sola_y_publicar_los_dos_eventos_si_el_equipo_completa_el_cupo(
    client, db, comportamiento, cola_de_eventos
):
    _, _, liga = crear_liga_con_equipos(db, 3, max_teams=4)  # falta un equipo para completar
    league_id = liga.league_id
    rival = crear_usuario(db, "rival")
    body = armar_body(rival, crear_jugadores(db, rival.team_id))

    # el rival solicita unirse a la liga mediante el endpoint POST /api/v1/leagues/{league_id}/teams,
    # autenticandose como el usuario que la creo.
    r = client.post(f"{URL}/{league_id}/teams", json=body.model_dump(), headers=headers(rival))

    assert r.status_code == 201
    assert estado_de(db, league_id) == LeagueStatus.IN_PROGRESS # la liga se inicia sola al completar el cupo
    assert contar_partidos(db, league_id) == 6 
    assert leer_eventos(cola_de_eventos) == [  # se publican los dos eventos
        {"event": "TEAM_JOINED_LEAGUE", "data": {"league_id": league_id, "team_id": rival.team_id}},
        {"event": "LEAGUE_INITIATED",
         "data": {"league_id": league_id, "league_name": "Liga test", "max_teams": 4, "status": "IN_PROGRESS"}},
    ]


def test_deberia_seguir_pending_si_el_equipo_no_completa_el_cupo(
    client, db, comportamiento, cola_de_eventos
):
    _, _, liga = crear_liga_con_equipos(db, 2, max_teams=4)  # con el que se une serian 3 de 4
    league_id = liga.league_id
    rival = crear_usuario(db, "rival")
    body = armar_body(rival, crear_jugadores(db, rival.team_id))

    r = client.post(f"{URL}/{league_id}/teams", json=body.model_dump(), headers=headers(rival))

    assert r.status_code == 201
    assert estado_de(db, league_id) == LeagueStatus.PENDING
    assert contar_partidos(db, league_id) == 0
    assert leer_eventos(cola_de_eventos) == [
        {"event": "TEAM_JOINED_LEAGUE", "data": {"league_id": league_id, "team_id": rival.team_id}},
    ]