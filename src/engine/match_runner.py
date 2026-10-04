"""
Ciclo tick a tick del partido.

Lo que YA está decidido y por eso vive directamente acá adentro:
  - Orden del ciclo: comportamientos -> aplicar intenciones -> detectar
    gol -> incrementar tick -> notificar.
  - Un error de un comportamiento nunca frena el ciclo: ese jugador
    recibe IDLE para ese tick y los demás siguen normalmente. Esto se
    implementa DIRECTAMENTE acá (run_tick atrapa la excepción por
    jugador), no es responsabilidad de quien pase `execute_behavior`.
  - current_action refleja la intención EJECUTADA por el jugador en el
    tick, no si "ganó" una disputa por la pelota contra otro jugador
    (eso lo decide, puertas adentro, apply_intentions).
  - Las intenciones de TODOS los jugadores se recolectan sobre el
    MISMO snapshot antes de aplicar ninguna: nadie tiene ventaja por
    estar antes en el diccionario de jugadores.
  - Al llegar a total_ticks: la fase pasa a FINISHED, se persiste el
    resultado (on_finished) ANTES de liberar el estado de memoria del
    registry (si el orden se invirtiera, se perdería el resultado).

Lo que TODAVÍA no está decidido, y por eso son parámetros inyectados en
vez de código fijo acá:
  - execute_behavior: hoy no existe un sandbox real (ticket de
    aislamiento de on_tick); acá se lo llama UNA VEZ POR JUGADOR para
    poder aislar sus excepciones una por una.
  - apply_intentions: qué le hace cada Intention a la pelota y a las
    posiciones -- acá vive el desempate de pateo simultáneo.
  - detect_goal: la regla exacta de gol. pitch.default_detect_goal es
    un placeholder razonable, no la decisión final.
  - notify / tick_interval_seconds: el canal WS de partido todavía no
    existe (src/realtime/ws_routes.py está vacío).
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Optional

from src.engine.intentions import ActionType, Intention
from src.engine.pitch import TeamSide
from src.engine.state import MatchPhase, MatchRegistry, MatchState

# Firmas de las piezas. Nombrarlas acá sirve de documentación de la
# interfaz que el motor espera, aunque hoy solo existan como stubs/fakes
# en los tests.
ExecuteBehavior = Callable[[MatchState, int], Intention]
ApplyIntentions = Callable[[MatchState, dict[int, Intention]], None]
DetectGoal = Callable[[MatchState], Optional[TeamSide]]
NotifyTick = Callable[[MatchState], Awaitable[None]]
OnFinished = Callable[[MatchState], None]


def run_tick(
    state: MatchState,
    *,
    execute_behavior: ExecuteBehavior,
    apply_intentions: ApplyIntentions,
    detect_goal: DetectGoal,
) -> None:
    """
    Ejecuta UN tick completo, mutando `state` in place.

    A propósito no tiene ningún `await` adentro: mientras eso se
    mantenga, nadie que lea `state` desde otra tarea de asyncio (por
    ejemplo, el handler de GET /matches/{id}/state) puede ver un
    estado a mitad de actualizar. asyncio sólo cede el control del
    event loop en un `await`, y acá no hay ninguno: la función corre
    de punta a punta sin interrupciones.
    """
    intentions: dict[int, Intention] = {}

    for player_id in state.on_pitch_player_ids():
        try:
            intention = execute_behavior(state, player_id)
        except Exception:
            # Un comportamiento no debe poder tirar abajo el ciclo ni
            # afectar a los demás jugadores.
            intention = Intention(ActionType.IDLE)

        intentions[player_id] = intention
        state.players[player_id].current_action = intention.action

    # Recién acá, con las intenciones de TODOS ya recolectadas, se
    # aplican. Si se aplicaran una por una arriba, el primer jugador
    # del diccionario siempre "ganaría" cualquier disputa por la
    # pelota, sin que nadie lo haya decidido.
    apply_intentions(state, intentions)

    scoring_side = detect_goal(state)
    if scoring_side is TeamSide.HOME:
        state.score.home += 1
    elif scoring_side is TeamSide.AWAY:
        state.score.away += 1

    state.current_tick += 1


async def run_match(
    state: MatchState,
    registry: MatchRegistry,
    *,
    execute_behavior: ExecuteBehavior,
    apply_intentions: ApplyIntentions,
    detect_goal: DetectGoal,
    notify: NotifyTick,
    tick_interval_seconds: float,
    on_finished: Optional[OnFinished] = None,
) -> None:
    """
    Corre el partido hasta FINISHED. Pensado para lanzarse como tarea
    de fondo: `asyncio.create_task(run_match(...))`.

    TODO (no bloquea esto, pero hay que decidirlo): qué pasa si esta
    función explota por algo que NO es un comportamiento de jugador
    (un error en apply_intentions, detect_goal o notify). Hoy se
    propaga hacia quien creó la tarea; el `finally` igual libera el
    estado del registry, pero nadie más se entera de que el partido
    murió a mitad de camino.
    """
    registry.add(state)
    try:
        while state.current_tick < state.total_ticks:
            run_tick(
                state,
                execute_behavior=execute_behavior,
                apply_intentions=apply_intentions,
                detect_goal=detect_goal,
            )
            await notify(state)
            await asyncio.sleep(tick_interval_seconds)

        state.phase = MatchPhase.FINISHED

        if on_finished is not None:
            # Persistir el resultado ANTES de liberar: si se invierte
            # el orden, el resultado final del partido se pierde.
            on_finished(state)
    finally:
        registry.remove(state.match_id)
