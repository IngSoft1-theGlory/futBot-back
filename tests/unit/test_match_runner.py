"""
Tests del ciclo tick a tick (run_tick y run_match).

aplicar primitivas, detectar gol, canal WS
se mockean acá con fakes simples: estos tests prueban EL ORQUESTADOR.
"""

import asyncio

import pytest

from src.engine.geometry_types import Point2D
from src.engine.intentions import ActionType, Intention
from src.engine.game_types import AttributeType
from src.engine._01_to_world.pitch import PITCH_LENGTH, PITCH_WIDTH, TeamSide, detect_goal
from src.engine._01_to_world.pitch import TeamSide
from src.engine.player_api import PlayerAPI
from src.engine.state import (
    MatchPhase,
    MatchRegistry,
    TeamMatchSetup,
    build_initial_state,
)
from src.engine.match_runner import run_match, run_tick
from src.schemas.lineup_config import LineupConfig, StartingPlayer, SubstitutePlayer

MATCH_ID = 1


ATTRIBUTES = {
    AttributeType.POWER: 80,
    AttributeType.AGILITY: 50,
    AttributeType.CONTROL: 60,
    AttributeType.SPEED: 80,
    AttributeType.STRENGTH: 50,
}


def _setup(team_id: int, side: TeamSide, base_player_id: int) -> TeamMatchSetup:
    roles = ["DEF_LEFT", "DEF_RIGHT", "FORWARD"]
    lineup = LineupConfig(
        formation_type="2-1",
        starting_players=[
            StartingPlayer(player_id=base_player_id + i, role=role, behavior_id=1)
            for i, role in enumerate(roles)
        ],
        substitute_players=[
            SubstitutePlayer(player_id=base_player_id + 3 + i, behavior_id=1)
            for i in range(3)
        ],
    )
    # los mismos atributos para los 6 jugadores del equipo
    attributes = {base_player_id + i: dict(ATTRIBUTES) for i in range(6)}
    return TeamMatchSetup(team_id=team_id, side=side, lineup=lineup, attributes=attributes)


def _build_state(total_ticks: int = 3):
    home = _setup(team_id=1, side=TeamSide.HOME, base_player_id=100)
    away = _setup(team_id=2, side=TeamSide.AWAY, base_player_id=200)
    return build_initial_state(MATCH_ID, total_ticks, home, away)


# --- Fakes de las piezas inyectadas ---
# Cada fake respeta la firma que run_tick/run_match esperan (ver los tipos
# en match_runner.py), pero no usa todos sus parámetros: el editor los
# marca como "is not accessed" y es esperado. Los fakes solo tienen que
# poder recibir los argumentos con los que el ciclo los llama.


def _idle_behavior(state, player_id) -> Intention:
    return Intention(ActionType.IDLE)


def _noop_apply(state, intentions) -> None:
    pass


def _no_goal(ball_position):
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

def test_deberia_una_excepcion_no_frenar_el_resto_del_ciclo():
    """El tick se completa igual: current_tick avanza y detect_goal/
    apply_intentions se siguen llamando."""
    state = _build_state()
    llamadas = {"apply": 0, "goal": 0}

    def apply_que_cuenta(state, intentions):
        llamadas["apply"] += 1

    def goal_que_cuenta(ball_position):
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

    run_tick(state, execute_behavior=_idle_behavior, apply_intentions=_noop_apply, detect_goal=lambda ball_position: ganador)

    assert state.score.home == home_esperado
    assert state.score.away == away_esperado


# --- run_match ---

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

    # La pelota del partido A está dentro del arco de AWAY (gol de HOME en
    # cada tick); la del B sigue en el centro. Se usa la regla real.
    state_a.ball.position = Point2D(PITCH_LENGTH, PITCH_WIDTH / 2)

    await asyncio.gather(
        run_match(
            state_a,
            registry,
            execute_behavior=_idle_behavior,
            apply_intentions=_noop_apply,
            detect_goal=detect_goal,
            notify=_noop_notify,
            tick_interval_seconds=0,
        ),
        run_match(
            state_b,
            registry,
            execute_behavior=_idle_behavior,
            apply_intentions=_noop_apply,
            detect_goal=detect_goal,
            notify=_noop_notify,
            tick_interval_seconds=0,
        ),
    )

    assert state_a.score.home == 2  # un gol por tick, 2 ticks
    assert state_b.score.home == 0
    assert state_a.current_tick == 2
    assert state_b.current_tick == 5


# --- Fallas de las piezas que NO son comportamientos ---
# Un bug en apply_intentions, detect_goal o notify no debe dejar el
# partido muerto a la mitad: el ciclo lo loguea y sigue. Estos fakes
# siempre lanzan una excepción y no usan sus parámetros ("is not
# accessed"): solo simulan una pieza rota que otro ticket implementará.


def _apply_que_falla(state, intentions) -> None:
    raise RuntimeError("bug en apply_intentions")


def _detect_goal_que_falla(ball_position):
    raise RuntimeError("bug en detect_goal")


async def _notify_que_falla(state) -> None:
    raise RuntimeError("bug en notify")


def test_deberia_run_tick_seguir_si_apply_intentions_falla():
    state = _build_state()

    run_tick(state, execute_behavior=_idle_behavior, apply_intentions=_apply_que_falla, detect_goal=_no_goal)

    assert state.current_tick == 1


def test_deberia_run_tick_seguir_sin_gol_si_detect_goal_falla():
    state = _build_state()

    run_tick(state, execute_behavior=_idle_behavior, apply_intentions=_noop_apply, detect_goal=_detect_goal_que_falla)

    assert state.current_tick == 1
    assert (state.score.home, state.score.away) == (0, 0)


@pytest.mark.asyncio
async def test_deberia_run_match_terminar_aunque_apply_detect_y_notify_fallen_siempre():
    state = _build_state(total_ticks=4)
    registry = MatchRegistry()
    resultados = []

    await run_match(
        state,
        registry,
        execute_behavior=_idle_behavior,
        apply_intentions=_apply_que_falla,
        detect_goal=_detect_goal_que_falla,
        notify=_notify_que_falla,
        tick_interval_seconds=0,
        on_finished=resultados.append,
    )

    assert state.current_tick == 4
    assert state.phase is MatchPhase.FINISHED
    assert resultados == [state]  # el resultado igual se guardó
    assert MATCH_ID not in registry
