"""
Puesta en marcha de un partido: leer su configuración de la base, armar el
estado inicial y lanzar el motor.

Lo que NO hace:
  - Construir y validar el estado inicial: engine.state.build_initial_state.
  - Ejecutar el ciclo tick a tick y registrar/liberar el estado:
    engine.match_runner.run_match.
  - Validar la alineación al guardarla: lineup_service.

Lo que SÍ hace:
  - prepare_match: base -> MatchState. Síncrona, sin efectos (no lanza
    nada). Pensada para llamarse ANTES del commit que pasa el partido a
    IN_PROGRESS: si lanza MatchInitializationError, el service que hace el
    join revierte la unión y el visitante recibe el error (el partido no
    queda IN_PROGRESS sin motor).
  - launch_match: lanza run_match como tarea de fondo. Va DESPUÉS del
    commit. Tiene que llamarse con el event loop corriendo (un endpoint
    `async def`, o una tarea async de BackgroundTasks): desde un endpoint
    `def` común, que FastAPI corre en un hilo, no hay loop y falla.
  - start_match: prepare_match + launch_match, para quien no necesita
    separar los dos pasos.
  - save_match_result / make_on_finished: persistir el marcador final.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from functools import partial

from sqlalchemy.orm import Session

from src.database.base import SessionLocal
from src.engine.match_runner import (
    ApplyIntentions,
    DetectGoal,
    ExecuteBehavior,
    NotifyTick,
    OnFinished,
    run_match,
)
from src.engine import pitch
from src.engine.pitch import FORMATION_POSITIONS, TeamSide
from src.engine.state import (
    LineupPlayer,
    MatchInitializationError,
    MatchPhase,
    MatchRegistry,
    MatchState,
    TeamMatchSetup,
    build_initial_state,
    match_registry,
)
from src.engine.timing import TICK_DURATION_SECONDS, VALID_MATCH_DURATIONS_MINUTES, total_ticks_for
from src.models import LineupEntry, MatchStatus
from src.realtime.match_broadcast import notify as broadcast_tick
from src.repositories.match_repository import get_lineup_entries, get_match_by_id

logger = logging.getLogger(__name__)

# Referencias fuertes a las tareas de partido en curso. asyncio solo guarda
# referencias débiles a las tareas: sin esto, el garbage collector puede
# cancelar un partido a la mitad.
_running_matches: set[asyncio.Task] = set()


# --- base -> estado inicial -------------------------------------------------


def _formation_from_roles(roles: set[str | None]) -> str | None:
    """La formación NO se persiste: se deduce de los roles de los titulares.
    Usa FORMATION_POSITIONS (la fuente de verdad del motor) para no
    duplicar la lista de formaciones."""
    for formation_type, positions in FORMATION_POSITIONS.items():
        if set(positions) == roles:
            return formation_type
    return None


def _team_setup(team_id: int, side: TeamSide, entries: list[LineupEntry]) -> TeamMatchSetup:
    starter_roles = {entry.role for entry in entries if entry.is_starter}
    formation_type = _formation_from_roles(starter_roles)
    if formation_type is None:
        raise MatchInitializationError(
            f"No se pudo deducir la formación del equipo {team_id} a partir de los roles {sorted(map(str, starter_roles))}."
        )

    # Hoy el estado del motor solo necesita estos 4 campos de la alineación.
    # Cuando el ticket del snapshot sume los atributos PACSS, se completan
    # acá (Player ya los tiene) y en LineupPlayer.
    players = [
        LineupPlayer(
            player_id=entry.player_id,
            is_starter=entry.is_starter,
            role=entry.role,
            behavior_id=entry.behavior_id,
        )
        for entry in entries
    ]
    return TeamMatchSetup(team_id=team_id, formation_type=formation_type, side=side, players=players)


def prepare_match(session: Session, match_id: int) -> MatchState:
    """
    Lee el partido y sus alineaciones y devuelve el MatchState inicial.
    El anfitrión juega de HOME y el visitante de AWAY.

    Lanza MatchInitializationError si falta algo o es inconsistente
    (partido inexistente o ya terminado, sin visitante, duración inválida,
    alineación faltante, roles que no forman una formación conocida, y todo
    lo que valida build_initial_state). No registra ni lanza nada.
    """
    match = get_match_by_id(session, match_id)
    if match is None:
        raise MatchInitializationError(f"El partido {match_id} no existe.")
    if match.status is MatchStatus.FINISHED:
        raise MatchInitializationError(f"El partido {match_id} ya terminó.")
    if match.team_away_id is None:
        raise MatchInitializationError(f"El partido {match_id} todavía no tiene equipo visitante.")
    if match.match_duration not in VALID_MATCH_DURATIONS_MINUTES:
        raise MatchInitializationError(
            f"Duración inválida para el partido {match_id}: {match.match_duration} "
            f"(válidas: {VALID_MATCH_DURATIONS_MINUTES})."
        )

    entries_by_team: dict[int, list[LineupEntry]] = {match.team_host_id: [], match.team_away_id: []}
    for entry in get_lineup_entries(session, match_id):
        if entry.team_id not in entries_by_team:
            raise MatchInitializationError(
                f"El partido {match_id} tiene una alineación del equipo {entry.team_id}, que no participa."
            )
        entries_by_team[entry.team_id].append(entry)

    for team_id, entries in entries_by_team.items():
        if not entries:
            raise MatchInitializationError(f"El equipo {team_id} no tiene alineación en el partido {match_id}.")

    home = _team_setup(match.team_host_id, TeamSide.HOME, entries_by_team[match.team_host_id])
    away = _team_setup(match.team_away_id, TeamSide.AWAY, entries_by_team[match.team_away_id])

    return build_initial_state(match_id, total_ticks_for(match.match_duration), home, away)


# --- resultado final --------------------------------------------------------


def save_match_result(session: Session, match_id: int, home_goals: int, away_goals: int) -> None:
    """Guarda el marcador final y pasa el partido a FINISHED."""
    match = get_match_by_id(session, match_id)
    if match is None:
        raise LookupError(f"No se puede guardar el resultado: el partido {match_id} no existe.")

    match.home_goals = home_goals
    match.away_goals = away_goals
    match.status = MatchStatus.FINISHED
    session.commit()


def make_on_finished(session_factory: Callable[[], Session] = SessionLocal) -> OnFinished:
    """
    El on_finished de run_match. Abre su PROPIA sesión: el motor corre
    mucho después de que se cerró la del request que lo inició. Si guardar
    falla, la excepción sube a la tarea (que la loguea, ver _on_task_done)
    y run_match igual libera el estado de memoria.
    """

    def on_finished(state: MatchState) -> None:
        with session_factory() as session:
            save_match_result(session, state.match_id, state.score.home, state.score.away)

    return on_finished


# --- lanzamiento ------------------------------------------------------------


def _on_task_done(
    task: asyncio.Task,
    state: MatchState,
    on_finished: OnFinished,
    registry: MatchRegistry,
) -> None:
    """
    Si el motor murió con un error que el ciclo no atrapó, lo loguea y
    guarda el marcador del momento como resultado final, para que el
    partido no quede colgado en IN_PROGRESS. No lo hace si:
      - la fase ya era FINISHED: el error fue guardar el resultado mismo,
        y reintentarlo con la misma base no sirve;
      - el registry todavía tiene un estado para este partido: lo tiene
        otro motor, no hay que pisarle el resultado.
    """
    _running_matches.discard(task)
    if task.cancelled() or task.exception() is None:
        return

    logger.error("El partido %s terminó con error.", task.get_name(), exc_info=task.exception())

    if state.phase is MatchPhase.FINISHED or registry.get(state.match_id) is not None:
        return

    state.phase = MatchPhase.FINISHED
    try:
        on_finished(state)
    except Exception:
        logger.exception("No se pudo guardar el resultado parcial del partido %s.", state.match_id)


def launch_match(
    state: MatchState,
    *,
    execute_behavior: ExecuteBehavior,
    apply_intentions: ApplyIntentions,
    detect_goal: DetectGoal = pitch.detect_goal,
    notify: NotifyTick = broadcast_tick,
    on_finished: OnFinished | None = None,
    registry: MatchRegistry = match_registry,
    tick_interval_seconds: float = TICK_DURATION_SECONDS,
) -> asyncio.Task:
    """
    Lanza run_match como tarea de fondo y devuelve la tarea. Requiere el
    event loop corriendo (si no, RuntimeError). Si el motor muere con un
    error inesperado, se guarda el resultado parcial (ver _on_task_done).
    execute_behavior y
    apply_intentions se reciben porque las piezas reales las aportan los
    tickets del sandbox de on_tick y de kick_ball.
    """
    loop = asyncio.get_running_loop()

    # run_match registra el estado recién cuando la tarea arranca: sin este
    # chequeo, un segundo arranque del mismo partido fallaría dentro de la
    # tarea, donde nadie lo ve.
    if state.match_id in registry:
        raise MatchInitializationError(f"El partido {state.match_id} ya tiene un motor corriendo.")

    on_finished = on_finished if on_finished is not None else make_on_finished()

    task = loop.create_task(
        run_match(
            state,
            registry,
            execute_behavior=execute_behavior,
            apply_intentions=apply_intentions,
            detect_goal=detect_goal,
            notify=notify,
            tick_interval_seconds=tick_interval_seconds,
            on_finished=on_finished,
        ),
        name=f"match-{state.match_id}",
    )
    _running_matches.add(task)
    task.add_done_callback(partial(_on_task_done, state=state, on_finished=on_finished, registry=registry))
    return task


def start_match(session: Session, match_id: int, **launch_kwargs) -> asyncio.Task:
    """prepare_match + launch_match. Si la preparación falla, el motor no se lanza."""
    return launch_match(prepare_match(session, match_id), **launch_kwargs)
