"""
Logica de ejecucion de ligas
"""

from __future__ import annotations 

import logging
import asyncio
from collections.abc import Callable, Coroutine

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
        advance_league(session, SessionLocal, match.league_id, match.round_number) # arranco la fecha siguiente si corresponde
        return

    # lanzo el motor
    launch_match(
        state, 
        execute_behavior=execute_behavior, 
        apply_intentions=apply_intentions,
        on_finished=make_on_finished(),
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


def advance_league(
    session: Session, session_factory: Callable[[], Session], league_id: int, round_number: int
) -> None:
    """
    Se llama al termina un partido de liga, si era el ultimo partido de la fecha,
    arranca la siguiente en segundo plano, si aun quedan partidos en progreso, o era la ultima
    fecha, no arranca nada
 
    session es la que se usa para decidir ahora. session_factory es para que la fecha,
    siguiente abra su propia sesion, porque esta puede estar cerrada para cuando arranque
    """
    next_round = next_round_to_start(session, league_id, round_number)
    if next_round is None:
        return
 
   # se crea la tarea que va a arrancar la siguiente fecha
    start_round_job = _start_round(session_factory, league_id, next_round)
 
    # se  manda a correr en segundo plano, sin esperar a que termine
    _run_in_background(start_round_job)


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
    # si la liga no tiene partidos o ya estamos en la ultima fecha, no hay siguiente fecha
    if last_round_number is None or round_number >= last_round_number:
        return None

    # se terminaron los partidos de le fecha y se puede arrancar la siguiente fecha 
    return round_number + 1

 
# asyncio guarda referencias de las tareas (debiles), ya si no se guardan, el garbage
# collector puede cancelar una tarea a la mitad, por eso se guardan aca mientras corren
_background_tasks: set[asyncio.Task] = set()
 
 
def _run_in_background(coroutine: Coroutine) -> None:
    """
    Manda a ejecutar un trabajo async en segundo plano y sigue de largo, sin esperar a que termine
 
    Se usa para arrancar la fecha siguiente, on_finished es una funcion comun (NO async), asi que
    no puede hacer await y quedarse esperando a que la fecha arranque, por lo que se le pide al
    event loop que ejecute el trabajo cuando pueda y vuelve enseguida
 
    coroutine es ese trabajo, es lo que devuelve al llamar a una funcion async def, ejemplo
    _start_round(...), llamar a esa funcion no ejecuta nada, solo deja el trabajo armado
    """

    # el event loop ejecuta el codigo async del servidor, pido el que esta corriendo ahora, 
    # ejecuta una tarea (task) y sigo sin esperarla
    task = asyncio.get_running_loop().create_task(coroutine)
 
    # guardo la tarea en el set para que Python no la borre mientras corre (motivo arriba del set)
    _background_tasks.add(task)
 
    # cuando la tarea termina, se llama a discard con ella y la saca del set
    task.add_done_callback(_background_tasks.discard)
 
 
async def _start_round(session_factory: Callable[[], Session], league_id: int, round_number: int) -> None:
    """
    Arranca una fecha desde la tarea de fondo, con una sesion propia, si falla, lo deja en el log 
    nadie mas lo va a ver
    """
    try:
        with session_factory() as session: # se abre una sesion nueva para arrancar la fecha, porque la que llamo 
                                            # a advance_league puede estar cerrada cuando se ejecute esta tarea
            await start_league_round(session, league_id, round_number) # arranca todos los partidos PENDING de la fecha
    except Exception:
        logger.exception("No se pudo arrancar la fecha %s de la liga %s.", round_number, league_id)
