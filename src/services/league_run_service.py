"""
Logica de ejecucion de ligas
"""

from __future__ import annotations 

import logging

from sqlalchemy.orm import Session

from fastapi.concurrency import run_in_threadpool

from src.repositories.match_repository import get_match_by_id
from src.core.exceptions import MatchNotFoundError, MatchUnavailableError, InvalidConfigurationError
from src.models.match import MatchStatus, Match
from src.repositories.match_repository import claim_pending_league_match, get_pending_round_matches
from src.services.lineup_service import copy_league_lineup_to_match
from src.services.match_start_service import prepare_engine, save_match_result, launch_match
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
        # guardo los ids porque un rollback vacia los objetos Match, y leerlos de nuevo iria a la base
        match_ids = [match.match_id for match in pending_matches]
    except Exception:
        logger.exception("No se pudieron buscar los partidos de la fecha %s de la liga %s.", round_number, league_id)
        return

    # los arranco de a uno porque comparten la sesion, y una sesion no se puede usar en dos lugares a la vez, igual juegan en paralelo, start_league_match lanza el motor como tarea de fondo y no espera a que termine
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
        return

    # lanzo el motor
    launch_match(state, execute_behavior=execute_behavior, apply_intentions=apply_intentions)

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


