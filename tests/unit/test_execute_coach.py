"""
Tests de la ejecución del DT en el partido.
"""

import asyncio
from sqlalchemy import select

from src.engine._01_to_world.metrics import PauseType
from src.engine._01_to_world.pitch import TeamSide
from src.engine._02_to_match.state import MatchRegistry, build_initial_state, coach_registry
from src.engine.match_runner import run_match
from src.models import Behavior, BehaviorType
from src.services.match_start_service import load_coach_behaviors
from tests.unit.test_behavior_type import crear_en_base
from tests.unit.test_join_league_service import anfitrion, crear_usuario
from tests.unit.test_match_runner import (
    _build_state, _idle_behavior, _no_goal, _noop_apply, _noop_notify, _setup,
)

# el registry solo usa el id de la liga como clave, asi que no hace falta una liga real
LIGA_ID = 1


def _armar_estado(local, visitante):
    """Estado inicial con los team_id de los dos usuarios."""
    home = _setup(local.team_id, TeamSide.HOME, base_player_id=100)
    away = _setup(visitante.team_id, TeamSide.AWAY, base_player_id=200)
    return build_initial_state(1, 3, home, away)


# --- preparación ---

def test_deberia_cargar_el_dt_elegido_y_dejar_sin_dt_al_equipo_que_no_eligio(session, anfitrion):
    # limpio el registry para que no queden DTs elegidos por otros tests
    coach_registry._coaches.clear()

    rival = crear_usuario(session, "rival")
    dt = crear_en_base(session, anfitrion.user_id, BehaviorType.COACH)
    coach_registry.set(LIGA_ID, anfitrion.team_id, dt.behavior_id)  # solo el anfitrión elige DT
    state = _armar_estado(anfitrion, rival)

    load_coach_behaviors(session, state, LIGA_ID)

    # el anfitrión eligió DT: está cargado
    assert anfitrion.team_id in state.coach_on_ticks
    # el rival no eligió: no tiene DT
    assert rival.team_id not in state.coach_on_ticks

def test_deberia_dar_a_cada_equipo_los_predeterminados_y_los_de_jugador_propios(session, anfitrion):
    coach_registry._coaches.clear()

    rival = crear_usuario(session, "rival")
    predeterminado = session.scalars(select(Behavior).where(Behavior.is_default.is_(True))).one()

    propio = crear_en_base(session, anfitrion.user_id)  # comportamiento de jugador del anfitrión
    crear_en_base(session, anfitrion.user_id, BehaviorType.COACH)  # este no debería aparecer en la lista de lo q se le puede asignar a un jugador, porque es tipo coach
    state = _armar_estado(anfitrion, rival)

    load_coach_behaviors(session, state, LIGA_ID)

    # anfitrión tiene el predeterminado + el suyo, y sin el COACH
    assert set(state.behavior_codes_for_coach[anfitrion.team_id]) == {predeterminado.behavior_id, propio.behavior_id}
    # rival tiene solo el predeterminado, no ve los del anfitrión
    assert set(state.behavior_codes_for_coach[rival.team_id]) == {predeterminado.behavior_id}

# --- ejecución durante el partido ---

async def _jugar_con_dt(total_ticks):
    """Juega un partido donde el equipo 1 tiene DT. Anota (tick, en_pausa) cada vez que se lo ejecuta."""
    # armo un partido de prueba con total_ticks
    state = _build_state(total_ticks)
    # le digo al estado que el equipo 1 tiene DT. por q pone None entonces?
    state.coach_on_ticks[1] = None

    # acá voy a ir anotando, una entrada por cada vez que se ejecute el DT
    llamadas = []

    # en vez de correr el código de un DT, esta funcion solo anota en qué momento la llamaron: 
    # el tick actual y si había una pausa activa
    def execute_coach_falso(state, team_id):
        llamadas.append((state.current_tick, state.pause is not None))

    # juego el partido completo. El motor llama al DT falso después de cada tick
    # y al comenzar cada pausa, y cada llamada queda anotada en "llamadas"
    await run_match(
        state,
        MatchRegistry(),
        execute_behavior=_idle_behavior,   # los jugadores no hacen nada
        apply_intentions=_noop_apply,      # no se aplica ningún movimiento
        detect_goal=_no_goal,              # nunca hay gol
        notify=_noop_notify,               # no se avisa a nadie
        tick_interval_seconds=0,           # sin espera entre ticks
        pause_durations={PauseType.COOLING_BREAK: 0, PauseType.HALF_TIME: 0},  # pausas sin esperar
        execute_coach=execute_coach_falso, # el motor usa mi DT falso en vez del real
    )

    return llamadas


def test_deberia_ejecutar_el_dt_una_vez_por_cada_tick():
    # juego 3 ticks y me devuelve cada vez que el motor llama al DT falso
    llamadas = asyncio.run(_jugar_con_dt(total_ticks=3))  # con 3 ticks no hay pausas

    # me quedo con el tick de cada llamada
    ticks = []
    for tick, _ in llamadas:
        ticks.append(tick)

    # el motor llamó al DT una vez por tick
    assert ticks == [1, 2, 3]


def test_deberia_ejecutar_el_dt_una_vez_al_comenzar_cada_pausa_con_la_pausa_activa():
    # juego 240 ticks, que incluyen 3 pausas (ticks 60, 120 y 180)
    llamadas = asyncio.run(_jugar_con_dt(total_ticks=240))

    # me quedo solo con el tick de las llamadas que se hicieron durante una pausa
    ticks_en_pausa = []
    for tick, en_pausa in llamadas:
        if en_pausa:
            ticks_en_pausa.append(tick)

    # el motor llamó al DT una vez al comenzar cada pausa
    assert ticks_en_pausa == [60, 120, 180]
    # y en total 240 llamadas de ticks + 3 de pausas
    assert len(llamadas) == 240 + 3  