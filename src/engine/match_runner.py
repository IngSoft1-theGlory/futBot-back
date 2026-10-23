"""
Ciclo del partido, tick a tick.

- run_tick: juega UN tick (cada jugador decide, se aplican las
  decisiones, se cuenta el gol y avanza el reloj).
- run_match: repite run_tick hasta el final del partido. Después de
  cada tick avisa a los clientes (notify) y espera. Cuando llega a un
  tick de pausa (Cooling Break o Half-Time) el reloj se detiene y el
  partido espera en PAUSED antes de seguir.

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
import time
from typing import Awaitable, Callable, Optional

from src.engine._01_to_world.metrics import (
    PAUSE_DURATION_SECONDS,
    PauseSlot,
    PauseType,
    pause_schedule_for,
)
from src.engine._02_to_match.state import MatchPhase, MatchRegistry, MatchState, PauseState
from src.engine._01_to_world.pitch import TeamSide
from src.engine._01_to_world.data_types import Point2D, ActionType, Intention 


logger = logging.getLogger(__name__)

# Firmas de las piezas que run_match recibe por parámetro.
ExecuteBehavior = Callable[[MatchState, int], Intention]
ApplyIntentions = Callable[[MatchState, dict[int, Intention]], None]
DetectGoal = Callable[[Point2D], Optional[TeamSide]]
NotifyTick = Callable[[MatchState], Awaitable[None]]
OnFinished = Callable[[MatchState], None]
NotifyPause = Callable[[MatchState, PauseType, float, bool], Awaitable[None]]


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


async def _notify_pause_safely(
        notify_pause: Optional[NotifyPause], 
        state: MatchState, 
        pause_type: PauseType, 
        duration_seconds: float,
        started: bool,
) -> None:
    """ Avisa el inicio o el fin de una pausa,
    donde : el inicio (started=True) o el fin (started=False) """
    if notify_pause is None:
        return
    try: # si falla el notify_pause, no se interrumpe el partido: sigue corriendo aunque no se avise a los clientes
        await notify_pause(state, pause_type, duration_seconds, started)
    except Exception:
        logger.exception(
            "notify_pause falló al %s la pausa %s del partido %s; el partido sigue.",
            "iniciar" if started else "terminar",     
            pause_type.value,
            state.match_id,
        )


async def _run_pause(
        state: MatchState, 
        slot: PauseSlot, 
        duration_seconds: float, 
        notify_pause: Optional[NotifyPause] = None
) -> None:
    """
    Detiene el partido durante una pausa: pone PAUSED, crea state.pause, espera
    y vuelve a IN_PROGRESS. No toca current_tick ni ejecuta comportamientos.
    """
    state.phase = MatchPhase.PAUSED
    state.pause = PauseState(
        type=slot.type,
        number=slot.number,
        ends_at=time.monotonic() + duration_seconds,
    )

    # avisa a los clientes que empezó la pausa (Cooling Break o Half-Time)
    await _notify_pause_safely(notify_pause, state, slot.type, duration_seconds, started=True)

    # espera el tiempo de la pausa (Cooling Break o Half-Time)
    await asyncio.sleep(duration_seconds)

    # termina la pausa: vuelve a IN_PROGRESS y borra state.pause
    state.pause = None
    state.phase = MatchPhase.IN_PROGRESS

    # avisa a los clientes que terminó la pausa (Cooling Break o Half-Time)
    await _notify_pause_safely(notify_pause, state, slot.type, duration_seconds, started=False)


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
    pause_durations: dict[PauseType, float] = PAUSE_DURATION_SECONDS,
    notify_pause: Optional[NotifyPause] = None,
) -> None:
    """ 
    Corre el partido completo, tick a tick, hasta que pasa a FINISHED.
    Se lanza como tarea de fondo: asyncio.create_task(run_match(...)).

    Ver más info. en Documentación - "ABOUT_DESIGN" 
    """
    
    registry.add(state)  # el partido es registrado para que otros puedan consultarlo mientras corre
    try:
        pause_schedule = pause_schedule_for(state.total_ticks)
        next_pause = 0  # índice de la próxima pausa del calendario: así ninguna se repite
        while state.current_tick < state.total_ticks: 
            # Si toca pausa, el reloj se detiene: current_tick queda igual y no hay ticks ni notify
            if next_pause < len(pause_schedule) and state.current_tick == pause_schedule[next_pause].tick:
                slot = pause_schedule[next_pause]
                await _run_pause(state, slot, pause_durations[slot.type], notify_pause)
                next_pause += 1

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