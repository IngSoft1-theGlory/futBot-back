"""
Ciclo del partido, tick a tick.

- run_tick: juega UN tick (cada jugador decide, se aplican las
  decisiones, se cuenta el gol y avanza el reloj).
- run_match: repite run_tick hasta el final del partido. Después de
  cada tick avisa a los clientes (notify) y espera.

Las piezas que vienen de otros módulos (comportamientos, física, regla
de gol, aviso y guardado del resultado) se reciben por parámetro: así
los tests pueden pasar versiones falsas.

Si falla un comportamiento, la física, la regla de gol o el aviso, el
partido sigue: lo importante es que llegue a FINISHED.

Ver más info. en Documentación - "ABOUT_DESIGN"
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from src.engine.geometry_types import Point2D
from src.engine.intentions import ActionType, Intention
from src.engine.pitch import TeamSide
from src.engine.state import MatchPhase, MatchRegistry, MatchState

logger = logging.getLogger(__name__)

# Firmas de las piezas que todavía implementan otros tickets (o que
# siguen en discusión). Nombrarlas acá sirve de documentación de la
# interfaz que el motor espera, aunque hoy solo existan como stubs/fakes
# en los tests.
ExecuteBehavior = Callable[[MatchState, int], Intention]
ApplyIntentions = Callable[[MatchState, dict[int, Intention]], None]
DetectGoal = Callable[[Point2D], Optional[TeamSide]]
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
    Juega UN tick completo: cada jugador decide, se aplican las decisiones
    y se cuenta el gol. Modifica state directamente.

    No tiene ningún await a propósito.
    Ver más info. en Documentación - "ABOUT_DESIGN"
    """
    
    intentions: dict[int, Intention] = {} 

    for player_id in state.on_pitch_player_ids():
        try:
            intention = execute_behavior(state, player_id) # se devuelve la intención de cada jugador según su comportamiento
        except Exception:
            intention = Intention(ActionType.IDLE) # si falla un comportamiento, el jugador se va a quedar quieto (IDLE) 

        intentions[player_id] = intention
        state.players[player_id].current_action = intention.action
    
    # APLICACION: recién ahora, con las intenciones de TODOS juntas, 
    # se aplican. Si se aplicaran de a una arriba, el primer jugador del 
    # diccionario ganaría siempre las disputas por la pelota
    try:
        apply_intentions(state, intentions)
    except Exception:
        logger.exception(
            "apply_intentions falló en el tick %s del partido %s; el tick sigue sin aplicar movimientos.",
            state.current_tick,
            state.match_id,
        )

    try:
        scoring_side = detect_goal(state.ball.position) # detecta goles y devuelve el lado que marco gol.
    except Exception:
        logger.exception(
            "detect_goal falló en el tick %s del partido %s; se asume que no hubo gol.",
            state.current_tick,
            state.match_id,
        )
        scoring_side = None
    
    # suma de gol al equipo que corresponda, si hubo gol
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
    Corre el partido completo, tick a tick, hasta que pasa a FINISHED.
    Se lanza como tarea de fondo: asyncio.create_task(run_match(...)).

    Ver más info. en Documentación - "ABOUT_DESIGN" 
    """
    
    registry.add(state)  # el partido es registrado para que otros puedan consultarlo mientras corre
    try:
        while state.current_tick < state.total_ticks: 
            run_tick(
                state,
                execute_behavior=execute_behavior,
                apply_intentions=apply_intentions,
                detect_goal=detect_goal,
            )
            try:
                await notify(state) # avisa a los clientes del estado del partido después de cada tick
            except Exception:
                logger.exception(
                    "notify falló en el tick %s del partido %s; el partido sigue.",
                    state.current_tick,
                    state.match_id,
                )
            await asyncio.sleep(tick_interval_seconds) # espera el intervalo de tiempo entre ticks antes del proximo tick

        state.phase = MatchPhase.FINISHED

        if on_finished is not None:
            # Persistir el resultado ANTES de liberar: si se invierte
            # el orden, el resultado final del partido se pierde.
            on_finished(state)
    finally:
        registry.remove(state.match_id)