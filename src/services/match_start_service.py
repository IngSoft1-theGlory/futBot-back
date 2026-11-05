"""
Puesta en marcha de un partido: leer su configuración de la base, armar el
estado inicial y lanzar el motor.

 prepare_match y prepare_engine van antes del commit y launch_match despues, con el event loop corriendo.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from functools import partial

from sqlalchemy.orm import Session

from src.repositories.league_repository import get_league_by_id
from src.database.base import SessionLocal
from src.engine._01_to_world import pitch
from src.engine._01_to_world.pitch import FORMATION_POSITIONS, TeamSide
from src.engine._02_to_match.state import (
    MatchInitializationError,
    MatchPhase,
    MatchRegistry,
    MatchState,
    TeamMatchSetup,
    attributes_of,
    build_initial_state,
    match_registry,
)
from src.engine.match_runner import (
    ApplyIntentions,
    DetectGoal,
    ExecuteBehavior,
    NotifyTick,
    OnFinished,
    run_match,
    NotifyPause,
)
from src.engine._01_to_world.metrics import (
    PAUSE_DURATION_SECONDS, TICK_DURATION_SECONDS, VALID_MATCH_DURATIONS_MINUTES, PauseType, total_ticks_for
)
from src.models import LineupEntry, MatchStatus, Player, Match
from src.repositories.match_repository import get_lineup_entries, get_match_by_id, get_players_by_team, get_behaviors_by_ids
from src.realtime.match_broadcast import notify as broadcast_tick, notify_pause as broadcast_pause
from src.schemas.lineup_config import LineupConfig, StartingPlayer, SubstitutePlayer

from src.realtime.event_bus import event_bus # Necesario para lanzar el evento MATCH_FINISHED
from src.models.match import MatchStatus
from src.engine._03_to_builder.behavior_executor import assign_behavior, execute_behavior
from src.core.exceptions import InvalidConfigurationError

logger = logging.getLogger(__name__)

# Referencias fuertes a las tareas de partido en curso. asyncio solo guarda
# referencias débiles a las tareas: sin esto, el garbage collector puede
# cancelar un partido a la mitad.
_running_matches: set[asyncio.Task] = set()

LeagueMatchHook = Callable[[int, int], None]  # (league_id, round_number)

# --- base -> estado inicial -------------------------------------------------


def _formation_from_roles(roles: set[str | None]) -> str | None:
    """La formación NO se persiste: se deduce de los roles de los titulares.
    Usa FORMATION_POSITIONS (la fuente de verdad del motor) para no
    duplicar la lista de formaciones."""
    for formation_type, positions in FORMATION_POSITIONS.items():
        if set(positions) == roles:
            return formation_type
    return None


# Una alineación guardada tiene 3 titulares y 3 suplentes (lo valida lineup_service
# al guardarla). Se revisa de nuevo acá porque estos datos vienen de la base.
STARTERS_PER_TEAM = 3
SUBSTITUTES_PER_TEAM = 3


def _team_setup(
    team_id: int, side: TeamSide, entries: list[LineupEntry], players: list[Player]
) -> TeamMatchSetup:
    """
    Arma lo que un equipo aporta al motor: su LineupConfig (la formación se
    deduce de los roles) y los atributos de cada jugador, leídos de la
    tabla players (los atributos NO están en la alineación).
    """
    starters = [entry for entry in entries if entry.is_starter]
    substitutes = [entry for entry in entries if not entry.is_starter]

    if len(starters) != STARTERS_PER_TEAM or len(substitutes) != SUBSTITUTES_PER_TEAM:
        raise MatchInitializationError(
            f"El equipo {team_id} no tiene {STARTERS_PER_TEAM} titulares y {SUBSTITUTES_PER_TEAM} "
            f"suplentes (tiene {len(starters)} y {len(substitutes)})."
        )

    starter_roles = {entry.role for entry in starters}
    formation_type = _formation_from_roles(starter_roles)
    if formation_type is None:
        raise MatchInitializationError(
            f"No se pudo deducir la formación del equipo {team_id} a partir de los roles {sorted(map(str, starter_roles))}."
        )

    if any(entry.behavior_id is None for entry in entries):
        raise MatchInitializationError(f"Un jugador del equipo {team_id} no tiene comportamiento asignado.")

    lineup = LineupConfig(
        formation_type=formation_type,
        starting_players=[
            StartingPlayer(player_id=e.player_id, role=e.role, behavior_id=e.behavior_id) for e in starters
        ],
        substitute_players=[SubstitutePlayer(player_id=e.player_id, behavior_id=e.behavior_id) for e in substitutes],
    )
    attributes = {player.player_id: attributes_of(player) for player in players}
    return TeamMatchSetup(team_id=team_id, side=side, lineup=lineup, attributes=attributes)


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

    home = _team_setup(
        match.team_host_id, TeamSide.HOME, entries_by_team[match.team_host_id],
        get_players_by_team(session, match.team_host_id),
    )
    away = _team_setup(
        match.team_away_id, TeamSide.AWAY, entries_by_team[match.team_away_id],
        get_players_by_team(session, match.team_away_id),
    )

    if match.league_id is not None:
        league = get_league_by_id(session, match.league_id)
        if league.penalties_enabled is not None:
            penalties_e = league.penalties_enabled 
        else:
            penalties_e = False
    else: 
        penalties_e = False


    return build_initial_state(match_id, total_ticks_for(match.match_duration), home, away, penalties_e)


def prepare_engine(session: Session, match_id: int) -> tuple[MatchState, ExecuteBehavior]:
    """
    Arma lo que necesita el motor para arrancar, sin lanzarlo:
      - el MatchState inicial: prepare_match lee de la base las alineaciones de los
        dos equipos y los atributos PACSS de cada jugador (tabla players) y ubica
        a los titulares en la cancha
      - los comportamientos: a cada jugador se le asigna su propia función on_tick

    Cualquier falla se traduce a un error de negocio (400), nunca a un 500
    """
    try:
        state = prepare_match(session, match_id)
        ## los comportamientos de AMBAS alineaciones (host y rival), sin repetir ids: varios jugadores pueden usar el mismo comportamiento
        behavior_ids = {entry.behavior_id for entry in get_lineup_entries(session, match_id)}

        ## {behavior_id: codigo} sirve para buscar el codigo de cada jugador segun su behavior_id
        codes = {b.behavior_id: b.code for b in get_behaviors_by_ids(session, list(behavior_ids))} ## get_behaviors_by_ids devuelve solo los que existen
        
        ## si falta algun behavior_id, lo detecto acá y no recién en pleno partido
        faltantes = behavior_ids - codes.keys()
        if faltantes:
            raise MatchInitializationError(f"No existen los comportamientos {sorted(faltantes)}.")
        
        ## a cada jugador (titulares y suplentes) le asigno su comportamiento: assign_behavior compila su codigo y se lo guarda.
        ## un codigo sin on_tick (ValueError) o con errores de sintaxis/ejecución falla aca

        for player in state.players.values(): # values me permite acceder al valor del dict en vez de la key
            assign_behavior(player, player.behavior_id, codes[player.behavior_id]) # codes es un diccionario, le paso el behavior_id del jugador como clave para que retorne el codigo (str)

    except Exception as exc:
        """
         Atrapo Exception (no solo MatchInitializationError) porque assign_behavior
         ejecuta código escrito por usuarios (exec): puede tirar ValueError (sin on_tick),
         SyntaxError, NameError, etc. Todos son "el partido no se puede preparar",
         un error del usuario y no un bug del servidor: se devuelve como 400
         "from exc" conserva el error original para los logs
        """
        raise InvalidConfigurationError(f"No se pudo preparar el partido: {exc}") from exc

    return state, execute_behavior


# --- resultado final --------------------------------------------------------


def save_match_result(session: Session, match_id: int, home_goals: int, away_goals: int) -> Match:
    """Guarda el marcador final y publica los eventos correspondientes."""
    match = get_match_by_id(session, match_id)
    if match is None:
        raise LookupError(f"No se puede guardar el resultado: el partido {match_id} no existe.")

    match.home_goals = home_goals
    match.away_goals = away_goals
    match.status = MatchStatus.FINISHED
    session.commit()

    # Los eventos se publican DESPUES del commit: quien los recibe ya ve el resultado guardado.
    match_finished_event = {
        "match_id": match.match_id,
        "status": match.status.value,
    }
    if match.league_id is not None:
        match_finished_event["league_id"] = match.league_id  # solo los partidos de liga lo traen

    event_bus.publish("MATCH_FINISHED", match_finished_event)

    if match.league_id is not None:
        event_bus.publish("LEAGUE_MATCH_FINISHED", {
            "league_id": match.league_id,
            "match_id": match.match_id,
            "score": {"home": match.home_goals, "away": match.away_goals},
            "status": match.status.value,
        })

    return match


def make_on_finished(
        session_factory: Callable[[], 
        Session] = SessionLocal, 
        after_league_match: LeagueMatchHook | None = None
) -> OnFinished:
    """
    El on_finished de run_match. Abre su PROPIA sesión: el motor corre
    mucho después de que se cerró la del request que lo inició. Si guardar
    falla, la excepción sube a la tarea (que la loguea, ver _on_task_done)
    y run_match igual libera el estado de memoria.
    """

    def on_finished(state: MatchState) -> None:
        with session_factory() as session:
            
            match = save_match_result(session, state.match_id, state.score.home, state.score.away)

            # si el partido era de liga, se comprueba si se puede iniciar la siguiente fecha
            if after_league_match is not None and match.league_id is not None:
                after_league_match(match.league_id, match.round_number)

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
    # Si no lo reenviamos pause_durations, run_match usaría siempre sus valores por defecto y los tests 
    # que pasan por launch_match (ver test_join_friendly_motor) 
    # no podrían poner las pausas en 0.
    pause_durations: dict[PauseType, float] = PAUSE_DURATION_SECONDS,
    notify_pause: NotifyPause | None = broadcast_pause,
) -> asyncio.Task:
    """
    Lanza run_match como tarea de fondo y devuelve la tarea. Requiere el
    event loop corriendo (si no, RuntimeError). Si el motor muere con un
    error inesperado, se guarda el resultado parcial (ver _on_task_done).
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
            pause_durations=pause_durations,
            notify_pause=notify_pause,
        ),
        name=f"match-{state.match_id}",
    )
    _running_matches.add(task)
    task.add_done_callback(partial(_on_task_done, state=state, on_finished=on_finished, registry=registry))
    return task


def start_match(session: Session, match_id: int, **launch_kwargs) -> asyncio.Task:
    """prepare_match + launch_match. Si la preparación falla, el motor no se lanza."""
    return launch_match(prepare_match(session, match_id), **launch_kwargs)
