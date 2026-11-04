"""
Logica de ejecucion de ligas
"""

from __future__ import annotations 

import logging
import asyncio
from collections.abc import Callable

from sqlalchemy.orm import Session

from fastapi.concurrency import run_in_threadpool

from src.database.base import SessionLocal

from src.repositories.league_repository import get_league_by_id
from src.repositories.match_repository import (
    get_match_by_id, 
    count_unfinished_round_matches, 
    get_last_round_number, 
    claim_pending_league_match, 
    get_pending_round_matches,
)
from src.core.exceptions import MatchNotFoundError, MatchUnavailableError, InvalidConfigurationError
from src.models.match import MatchStatus, Match
from src.services.lineup_service import copy_league_lineup_to_match
from src.services.match_start_service import (
    prepare_engine,
    save_match_result,
    launch_match,
    make_on_finished,
    LeagueMatchHook,
)
from src.engine._02_to_match.state import MatchState 
from src.engine.match_runner import ExecuteBehavior
from src.engine._04_to_physics.simulation import apply_intentions
from src.realtime.event_bus import event_bus

logger = logging.getLogger(__name__)

FIRST_ROUND_NUMBER = 1  # numero de la primera fecha de una liga (generate_fixture las numera desde 1)

async def start_league_round(session: Session, league_id: int, round_number: int) -> None:
    """
    Arranca todos los partidos PENDING de una fecha de la liga

    Se llama despues del commit que inicia la liga, si algo falla se registra en el log y no
    sale de esta funcion,porque la liga ya esta iniciada, un partido que no arranca
    no frena a los demas ni cambia la respuesta de quien la llama
    Llamarla dos veces no relanza partidos, solo agarra los que siguen PENDING
    """
    try:
        pending_matches = await run_in_threadpool(get_pending_round_matches, session, league_id, round_number)
        # guardo solo los ids: son numeros simples y un rollback no los afecta
        match_ids = [match.match_id for match in pending_matches]
    except Exception:
        logger.exception("No se pudieron buscar los partidos de la fecha %s de la liga %s.", round_number, league_id)
        return

    # se arrancan de a uno porque todos usan la misma sesion de la base,
    # pero juegan a la vez: start_league_match lanza el motor y no espera a que termine
    for match_id in match_ids:
        try:
            await start_league_match(session, match_id)
        except Exception:
            logger.exception("No se pudo arrancar el partido %s de la fecha %s de la liga %s.", match_id, round_number, league_id)
            session.rollback()  # si el error rompio la sesion, la dejo lista para el proximo partido


async def start_league_match(session: Session, match_id: int) -> None:
    """
    Arranca un partido de liga: lo prepara en un hilo aparte (begin_league_match),
    lanza el motor y publica MATCH_STARTED (con league_id).
    Si el partido no se puede preparar, lo cierra 0-0 (FINISHED) para no trabar la liga
    y no lanza el motor ni publica MATCH_STARTED.
    Si el partido no existe o ya empezó, lanza MatchNotFoundError o MatchUnavailableError.
    """
    try:
        match, state, execute_behavior = await run_in_threadpool(begin_league_match, session, match_id) # uso run in threaadpool con await y async def porque begin league match accede y modifica la base de datos, que es lento, y conviene hacerlo en otro hilo
    except InvalidConfigurationError:
        # si hay un error que impide arrancar el partido
        # el resultado del partido es 0-0
        logger.exception("El partido %s no se pudo preparar: se cierra 0-0.", match_id)
        save_match_result(session, match_id, 0, 0)

        match = get_match_by_id(session, match_id) # recargo el partido para tener el league_id y round_number
        resolve_league_round(session, SessionLocal, match.league_id, match.round_number) # si el partido no se pudo preparar, se intenta arrancar la siguiente fecha de la liga en segundo plano
        return

    # lanzo el motor
    launch_match(
        state, 
        execute_behavior=execute_behavior, 
        apply_intentions=apply_intentions,
        on_finished=make_on_finished(after_league_match=make_league_match_hook()),
    )

    # publico match_started con el league_id 
    event_bus.publish("MATCH_STARTED", {
        "match_id": match.match_id,
        "league_id": match.league_id,
        "team_host_id": match.team_host_id,
        "team_away_id": match.team_away_id,
        "status": match.status.value,
    })
    
def begin_league_match(session: Session, match_id: int) -> tuple[Match, MatchState, ExecuteBehavior]:
    """
    Pasa un partido de liga de PENDING a IN_PROGRESS y deja listo todo lo que necesita el motor:
    copia la alineación vigente de la liga, y prepara el estado inicial y los comportamientos.

    Lanzar el motor y publicar eventos es trabajo de quien la llama.
    """
    match = get_match_by_id(session, match_id)
    if match is None: 
        raise MatchNotFoundError("El partido no existe o fue cancelado.")

    if match.status is not MatchStatus.PENDING:
        raise MatchUnavailableError("El partido ya comenzó.")

    try:
        # paso el partido de liga de pendiente a in_progress
        pending_to_in_progress = claim_pending_league_match(session, match_id)

        if not pending_to_in_progress:
            raise MatchUnavailableError("El partido ya comenzó.")

        # copio al partido de liga la alineacion vigente que ambos equipos tienen en lineup_entries
        copy_league_lineup_to_match(session, match)

        session.flush() # cargo los cambios a la base de datos, sin hacer commit aun, para q prepare engine las pueda leer
        session.refresh(match)  # el cambio a in progress fue a la base y match sigue en PENDING en memoria, lo recargo para que diga IN_PROGRESS

        state, execute_behavior = prepare_engine(session, match_id)
    
        session.commit()
    except Exception:
        session.rollback() # si algo falla, deshago todo 
        raise

    return (match, state, execute_behavior)


_round_start_tasks: set[asyncio.Task] = set()

def next_round_to_start(session: Session, league_id: int, round_number: int) -> int | None:
    """
    Devuelve el numero de la siguiente fecha de la liga que se puede arrancar, 
    o None si no se puede arrancar ninguna
    """

    # se evita que dos partidos que terminan casi a la vez arranquen la siguiente 
    # fecha dos veces
    get_league_by_id(session, league_id, for_update=True)

    # si todavia quedan partidos de la fecha sin terminar, NO arranco la siguiente fecha
    unfinished = count_unfinished_round_matches(session, league_id, round_number)
    if unfinished > 0:
        return None

    # se obtiene el numero de la ultima fecha de la liga
    last_round_number = get_last_round_number(session, league_id)
    # entonces si no hay partidos o ya se termino fecha
    if last_round_number is None or round_number >= last_round_number:
        return None

    # se terminaron los partidos de le fecha y se puede arrancar la siguiente fecha 
    return round_number + 1

 
def resolve_league_round(
        session: Session, 
        session_factory: Callable[[], Session], 
        league_id: int, round_number: int
) -> None:
    """
    Comprueba si terminó la fecha actual y, si corresponde, 
    inicia la siguiente fecha en segundo plano
    """
    # si no hay fecha siguiente, no hago nada
    next_round = next_round_to_start(session, league_id, round_number)
    if next_round is None:
        return
 
    # arranco la siguiente fecha en segundo plano, para no bloquear el request que termino el partido
    # obtengo el loop de asyncio que esta corriendo en el hilo principal, para poder crear una tarea en segundo plano
    loop = asyncio.get_running_loop()
    task = loop.create_task(_start_round_in_background(session_factory, league_id, next_round)) # creo la tarea de fondo

    # agrego la tarea al set de tareas activas, para que no se pierda si falla y para poder loguear el error
    _round_start_tasks.add(task) 
    task.add_done_callback(_on_round_start_done) # agrego el callback para cuando termine la tarea
  
 
def _on_round_start_done(task: asyncio.Task) -> None:
    """
    Procesa el resultado de la tarea que inició la siguiente fecha,
    elimina la tarea de las tareas activas y registra cualquier error
    """
    
    # la tarea ya terminó, se elimina de las tareas activas.
    _round_start_tasks.discard(task)
    # registra el error si la tarea terminó con una excepción.
    if not task.cancelled() and task.exception() is not None:
        logger.error("No se pudo arrancar la fecha siguiente de la liga.", exc_info=task.exception())

 
def make_league_match_hook(session_factory: Callable[[], Session] = SessionLocal) -> LeagueMatchHook:
    """
    Crea el callback que se ejecuta cuando termina un partido de liga
    """
    # hook trata de arrancar la siguiente fecha de la liga en segundo plano si ya terminaron todos 
    # los partidos de la fecha
    def hook(league_id: int, round_number: int) -> None:
        # si la fecha termino, arranca la siguiente fecha en segundo plano
        with session_factory() as session:
            resolve_league_round(session, session_factory, league_id, round_number)
 
    return hook
 

async def _start_round_in_background(
    session_factory: Callable[[], Session], league_id: int, round_number: int
) -> None:
    """
    Cuerpo de la tarea de fondo: abre una sesion propia y arranca la fecha.
    start_league_round ya es idempotente (solo toma los partidos PENDING) y no deja salir errores.
    """
    with session_factory() as session:
        await start_league_round(session, league_id, round_number)
