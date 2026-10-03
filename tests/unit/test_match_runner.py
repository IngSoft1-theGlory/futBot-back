"""
Tests del ciclo tick a tick (run_tick y run_match).

Las piezas todavía no implementadas en otros tickets (ejecución de
comportamientos en sandbox, aplicar primitivas, detectar gol, canal WS)
se mockean acá con fakes simples: este ticket prueba EL ORQUESTADOR,
no esas piezas.
"""

import asyncio

import pytest

from src.engine.geometry_types import Point2D
from src.engine.intentions import ActionType, Intention
from src.engine.pitch import TeamSide
from src.engine.player_api import PlayerAPI
from src.engine.state import (
    LineupPlayer,
    MatchPhase,
    MatchRegistry,
    TeamMatchSetup,
    build_initial_state,
)
from src.engine.match_runner import run_match, run_tick

MATCH_ID = 1


def _setup(team_id: int, side: TeamSide, base_player_id: int) -> TeamMatchSetup:
    roles = ["DEF_LEFT", "DEF_RIGHT", "FORWARD"]
    starters = [
        LineupPlayer(player_id=base_player_id + i, is_starter=True, role=role, behavior_id=1)
        for i, role in enumerate(roles)
    ]
    substitutes = [
        LineupPlayer(player_id=base_player_id + 3 + i, is_starter=False, role=None, behavior_id=1)
        for i in range(3)
    ]
    return TeamMatchSetup(team_id=team_id, formation_type="2-1", side=side, players=starters + substitutes)


def _build_state(total_ticks: int = 3):
    home = _setup(team_id=1, side=TeamSide.HOME, base_player_id=100)
    away = _setup(team_id=2, side=TeamSide.AWAY, base_player_id=200)
    return build_initial_state(MATCH_ID, total_ticks, home, away)


# --- Fakes de las piezas inyectadas ---


def _idle_behavior(state, player_id) -> Intention:
    return Intention(ActionType.IDLE)


def _noop_apply(state, intentions) -> None:
    pass


def _no_goal(state):
    return None


async def _noop_notify(state) -> None:
    pass


# --- run_tick ---


def test_deberia_run_tick_incrementar_current_tick_en_uno():
    state = _build_state()

    run_tick(state, execute_behavior=_idle_behavior, apply_intentions=_noop_apply, detect_goal=_no_goal)

    assert state.current_tick == 1


def test_deberia_run_tick_actualizar_current_action_de_cada_titular():
    state = _build_state()

    def kick_behavior(state, player_id):
        return Intention(ActionType.KICK_BALL)

    run_tick(state, execute_behavior=kick_behavior, apply_intentions=_noop_apply, detect_goal=_no_goal)

    for player_id in state.on_pitch_player_ids():
        assert state.players[player_id].current_action == ActionType.KICK_BALL


def test_deberia_run_tick_no_llamar_al_comportamiento_de_los_suplentes():
    state = _build_state()
    llamados = []

    def behavior_que_registra(state, player_id):
        llamados.append(player_id)
        return Intention(ActionType.IDLE)

    run_tick(state, execute_behavior=behavior_que_registra, apply_intentions=_noop_apply, detect_goal=_no_goal)

    suplentes = [pid for pid, p in state.players.items() if not p.is_starter]
    assert set(llamados).isdisjoint(suplentes)
    assert len(llamados) == 6  # 3 titulares x 2 equipos


def test_deberia_aislar_la_excepcion_de_un_solo_jugador():
    """Si el comportamiento del jugador 101 explota, 101 recibe IDLE
    y los demás jugadores no se ven afectados (siguen recibiendo su
    intención real)."""
    state = _build_state()

    def behavior_con_un_jugador_roto(state, player_id):
        if player_id == 101:
            raise RuntimeError("comportamiento roto")
        return Intention(ActionType.KICK_BALL)

    run_tick(
        state, execute_behavior=behavior_con_un_jugador_roto, apply_intentions=_noop_apply, detect_goal=_no_goal
    )

    assert state.players[101].current_action == ActionType.IDLE
    otros_titulares = [pid for pid in state.on_pitch_player_ids() if pid != 101]
    assert all(state.players[pid].current_action == ActionType.KICK_BALL for pid in otros_titulares)


def test_deberia_run_to_con_argumentos_invalidos_dejar_al_jugador_en_idle_sin_frenar_el_ciclo():
    """Un on_tick que llama run_to con speed_percentage inválido: el
    ValueError lo atrapa run_tick, ese jugador queda IDLE, los demás
    corren normalmente y el tick se completa."""
    state = _build_state()

    def behavior_con_run_to(state, player_id):
        api = PlayerAPI(game_state=None, attributes={})
        speed_percentage = 5.0 if player_id == 101 else 1.0  # 5.0 es inválido
        api.run_to(Point2D(50, 30), speed_percentage)
        return api.intention

    run_tick(state, execute_behavior=behavior_con_run_to, apply_intentions=_noop_apply, detect_goal=_no_goal)

    assert state.players[101].current_action == ActionType.IDLE
    otros_titulares = [pid for pid in state.on_pitch_player_ids() if pid != 101]
    assert all(state.players[pid].current_action == ActionType.RUN_TO for pid in otros_titulares)
    assert state.current_tick == 1


def test_deberia_una_excepcion_no_frenar_el_resto_del_ciclo():
    """El tick se completa igual: current_tick avanza y detect_goal/
    apply_intentions se siguen llamando."""
    state = _build_state()
    llamadas = {"apply": 0, "goal": 0}

    def apply_que_cuenta(state, intentions):
        llamadas["apply"] += 1

    def goal_que_cuenta(state):
        llamadas["goal"] += 1
        return None

    def behavior_roto(state, player_id):
        raise RuntimeError("explota siempre")

    run_tick(state, execute_behavior=behavior_roto, apply_intentions=apply_que_cuenta, detect_goal=goal_que_cuenta)

    assert state.current_tick == 1
    assert llamadas["apply"] == 1
    assert llamadas["goal"] == 1


def test_deberia_recolectar_todas_las_intenciones_antes_de_aplicar_ninguna():
    """apply_intentions recibe el diccionario COMPLETO de una sola vez,
    no una llamada por jugador: nadie se procesa antes que el resto."""
    state = _build_state()
    recibido = {}

    def apply_que_guarda(state, intentions):
        recibido.update(intentions)

    run_tick(state, execute_behavior=_idle_behavior, apply_intentions=apply_que_guarda, detect_goal=_no_goal)

    assert set(recibido.keys()) == set(state.on_pitch_player_ids())


@pytest.mark.parametrize(
    "ganador, home_esperado, away_esperado",
    [(TeamSide.HOME, 1, 0), (TeamSide.AWAY, 0, 1), (None, 0, 0)],
)
def test_deberia_actualizar_el_marcador_segun_detect_goal(ganador, home_esperado, away_esperado):
    state = _build_state()

    run_tick(state, execute_behavior=_idle_behavior, apply_intentions=_noop_apply, detect_goal=lambda s: ganador)

    assert state.score.home == home_esperado
    assert state.score.away == away_esperado


# --- run_match ---


@pytest.mark.asyncio
async def test_deberia_run_match_llegar_a_finished_al_agotar_los_ticks():
    state = _build_state(total_ticks=3)
    registry = MatchRegistry()

    await run_match(
        state,
        registry,
        execute_behavior=_idle_behavior,
        apply_intentions=_noop_apply,
        detect_goal=_no_goal,
        notify=_noop_notify,
        tick_interval_seconds=0,
    )

    assert state.phase == MatchPhase.FINISHED
    assert state.current_tick == 3


@pytest.mark.asyncio
async def test_deberia_run_match_notificar_una_vez_por_tick():
    state = _build_state(total_ticks=3)
    registry = MatchRegistry()
    notificaciones = []

    async def notify_que_cuenta(state):
        notificaciones.append(state.current_tick)

    await run_match(
        state,
        registry,
        execute_behavior=_idle_behavior,
        apply_intentions=_noop_apply,
        detect_goal=_no_goal,
        notify=notify_que_cuenta,
        tick_interval_seconds=0,
    )

    assert notificaciones == [1, 2, 3]


@pytest.mark.asyncio
async def test_deberia_run_match_liberar_el_estado_del_registry_al_terminar():
    state = _build_state(total_ticks=2)
    registry = MatchRegistry()

    await run_match(
        state,
        registry,
        execute_behavior=_idle_behavior,
        apply_intentions=_noop_apply,
        detect_goal=_no_goal,
        notify=_noop_notify,
        tick_interval_seconds=0,
    )

    assert registry.get(MATCH_ID) is None


@pytest.mark.asyncio
async def test_deberia_run_match_persistir_el_resultado_antes_de_liberar():
    """on_finished debe poder leer el estado (todavía en el registry)
    en el momento en que se lo llama."""
    state = _build_state(total_ticks=1)
    registry = MatchRegistry()
    observado = {}

    def on_finished(state):
        observado["estado_en_registry"] = registry.get(state.match_id)
        observado["phase"] = state.phase

    await run_match(
        state,
        registry,
        execute_behavior=_idle_behavior,
        apply_intentions=_noop_apply,
        detect_goal=_no_goal,
        notify=_noop_notify,
        tick_interval_seconds=0,
        on_finished=on_finished,
    )

    assert observado["phase"] == MatchPhase.FINISHED
    assert observado["estado_en_registry"] is state  # todavía no se había liberado


@pytest.mark.asyncio
async def test_deberia_run_match_liberar_el_estado_aunque_explote_despues_del_loop():
    """Si on_finished explota, el registry igual libera el estado (el
    finally no depende de que on_finished salga bien)."""
    state = _build_state(total_ticks=1)
    registry = MatchRegistry()

    def on_finished_roto(state):
        raise RuntimeError("falló al persistir")

    with pytest.raises(RuntimeError):
        await run_match(
            state,
            registry,
            execute_behavior=_idle_behavior,
            apply_intentions=_noop_apply,
            detect_goal=_no_goal,
            notify=_noop_notify,
            tick_interval_seconds=0,
            on_finished=on_finished_roto,
        )

    assert registry.get(MATCH_ID) is None


@pytest.mark.asyncio
async def test_deberia_dos_partidos_simultaneos_no_compartir_estado():
    """Dos run_match corriendo con asyncio.gather no se pisan entre sí."""
    state_a = _build_state(total_ticks=2)
    state_b = build_initial_state(
        2, 5, _setup(team_id=1, side=TeamSide.HOME, base_player_id=100), _setup(team_id=2, side=TeamSide.AWAY, base_player_id=200)
    )
    registry = MatchRegistry()

    async def goleador_de_a(state):
        pass

    def detect_goal_solo_en_a(state):
        return TeamSide.HOME if state.match_id == 1 else None

    await asyncio.gather(
        run_match(
            state_a,
            registry,
            execute_behavior=_idle_behavior,
            apply_intentions=_noop_apply,
            detect_goal=detect_goal_solo_en_a,
            notify=_noop_notify,
            tick_interval_seconds=0,
        ),
        run_match(
            state_b,
            registry,
            execute_behavior=_idle_behavior,
            apply_intentions=_noop_apply,
            detect_goal=detect_goal_solo_en_a,
            notify=_noop_notify,
            tick_interval_seconds=0,
        ),
    )

    assert state_a.score.home == 2  # un gol por tick, 2 ticks
    assert state_b.score.home == 0
    assert state_a.current_tick == 2
    assert state_b.current_tick == 5
