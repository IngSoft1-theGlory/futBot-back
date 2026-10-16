"""
Lógica de negocio de POST /api/v1/friendly.
"""

from __future__ import annotations

from typing import NamedTuple

from sqlalchemy.orm import Session

from src.engine._03_to_builder.behavior_executor import make_execute_behavior
from src.engine.match_runner import ExecuteBehavior
from src.engine._02_to_match.state import MatchInitializationError, MatchState
from src.models import Match, MatchStatus
from src.core.exceptions import InvalidConfigurationError, InvalidSettingsError, MatchNotFoundError,MatchUnavailableError
from src.repositories.match_repository import claim_pending_match, get_available_matches, get_behaviors_by_ids, get_lineup_entries, get_match_by_id
from src.schemas.friendly import CreateFriendlyRequest, JoinFriendlyRequest
from src.services.match_start_service import prepare_match
from src.services.lineup_service import save_lineup, validate_team_belongs_to_user, validate_match_duration, validate_min_players, validate_lineup

# Caso de uso 
def create_friendly(session: Session, user_id: int, payload: CreateFriendlyRequest) -> Match:
    """
    llama a las validaciones y, si todas pasan, guarda el Match y las 6 LineupEntry en una sola transacción
    """

    validate_team_belongs_to_user(session, user_id, payload.team_id)
    validate_match_duration(payload.match_duration)
    team_players = validate_min_players(session, payload.team_id)
    validate_lineup(session, payload, team_players, user_id)

    try:
        # el match y los 6 lineup entries se crean aca: si uno falla,
        # tiene que eliminarse todo (rollback) y no quedar nada guardado en la DB.

        # le paso a Match los param necesarios para crear un amistoso
        # (el id del rival es NULL porque todavía no se unió nadie)
        match = Match(
            team_host_id=payload.team_id,
            match_duration=payload.match_duration,
            status=MatchStatus.PENDING,
        )
        session.add(match)
        session.flush()  # guarda el match para conseguirle su id, pero todavía se puede deshacer

        # guardo la alineación del anfitrión en la DB 
        save_lineup(session, match.match_id, payload.team_id, payload)

        session.commit()  # recién acá queda guardado de verdad (match y lineup entries)

    except Exception:
        session.rollback()  # deshace todo lo de este intento, match incluido
        raise

    return match
                
def list_friendly_matches(
    session: Session, status: MatchStatus, page: int, limit: int) -> list[Match]:
    """
    Devuelve una página de amistosos filtrados por estado.
    """
    return get_available_matches(session, status=status, page=page, limit=limit)


def get_friendly(session: Session, match_id: int) -> Match:
    """
    Devuelve el amistoso con ese id. Si no existe, lanza MATCH_NOT_FOUND (404).
    """
    match = get_match_by_id(session, match_id)
    if match is None:
        raise MatchNotFoundError("El partido no existe o fue cancelado.")
    return match


class JoinedMatch(NamedTuple):
    """
    resultado de join_friendly: el partido ya confirmado y lo que necesita
    la ruta para lanzar el motor (launch_match) una vez hecho el commit,
    es una NamedTuple para poder desempaquetarla (match, state, execute_behavior = ...)
    y a la vez acceder por nombre (resultado.state).
    """

    match: Match                         # partido ya commiteado, IN_PROGRESS, con el rival
    state: MatchState                    # estado inicial del motor (12 jugadores con PACSS)
    execute_behavior: ExecuteBehavior    # corre el on_tick de cada jugador en cada tick


def join_friendly(session: Session, user_id: int, match_id: int, payload: JoinFriendlyRequest) -> JoinedMatch:
    """
    Inscribe al equipo rival en un amistoso en espera y lo pasa a IN_PROGRESS.
    Guarda el rival y su alineación en una sola transacción.

    Antes del commit prepara el partido (prepare_match) y arma el
    execute_behavior con los comportamientos de AMBAS alineaciones: si algo
    de eso falla se hace rollback y el error sale como error de negocio.
    Lanzar el motor (launch_match) es trabajo de la ruta, después del commit.
    """

    validate_team_belongs_to_user(session, user_id, payload.team_id)

    match = get_match_by_id(session, match_id)
    if match is None:
        raise MatchNotFoundError("El partido no existe o fue cancelado.")
    if match.status != MatchStatus.PENDING or match.team_away_id is not None:
        raise MatchUnavailableError("El partido ya comenzó o ya tiene rival.")
    # el anfitrion no puede jugar contra sí mismo
    if match.team_host_id == payload.team_id:
        raise InvalidSettingsError("El equipo no puede unirse a su propio partido.")

    team_players = validate_min_players(session, payload.team_id)
    validate_lineup(session, payload, team_players, user_id)

    try:
        # UPDATE condicional: si otro equipo se unio entre el chequeo de arriba
        # y aca, no actualiza ninguna fila y no se duplica la inscripcion
        if not claim_pending_match(session, match_id, payload.team_id):
            raise MatchUnavailableError("El partido ya comenzó o ya tiene rival.")

        save_lineup(session, match_id, payload.team_id, payload)
        """
         Hasta aca la alineacion del rival es solo un objeto en memoria y el match
         que tengo sigue mostrando "PENDING y sin rival" (el UPDATE de claim_pending_match
         fue directo a la base y no actualizo el objeto). prepare_match lee de la base,
         asi que antes necesito dos cosas:
           flush(): manda las LineupEntry nuevas a la base (esta sesion no tiene
                    autoflush), pero SIN commit: todavia se puede deshacer todo
           refresh(match): recarga el match con el rival y el estado IN_PROGRESS
        """
        session.flush()
        session.refresh(match)
        """
         todo lo que puede fallar del motor se hace ANTES del commit: si falla, el
         except de abajo hace rollback y el partido vuelve a quedar PENDING y sin
         rival (no queda un partido IN_PROGRESS que nadie va a correr)
        """
        state, execute_behavior = _prepare_engine(session, match_id)

        session.commit()

    except Exception:
        session.rollback()
        raise

    session.refresh(match)  ## el commit expira el objeto: lo recargo con el estado nuevo
    return JoinedMatch(match, state, execute_behavior)


def _prepare_engine(session: Session, match_id: int) -> tuple[MatchState, ExecuteBehavior]:
    """
    Arma lo que necesita el motor para arrancar, sin lanzarlo:
      - el MatchState inicial: prepare_match lee de la base las alineaciones de los
        dos equipos y los atributos PACSS de cada jugador (tabla players) y ubica
        a los titulares en la cancha
      - el execute_behavior: una funcion que, para un jugador y un tick, ejecuta el
        on_tick del comportamiento que ese jugador tiene asignado

    Cualquier falla se traduce a un error de negocio (400), nunca a un 500
    """
    try:
        state = prepare_match(session, match_id)
        ##los comportamientos de AMBAS alineaciones (host y rival), sin repetir ids: varios jugadores pueden usar el mismo comportamiento
        behavior_ids = {entry.behavior_id for entry in get_lineup_entries(session, match_id)}

        ## {behavior_id: codigo} es el formato que espera make_execute_behavior
        codes = {b.behavior_id: b.code for b in get_behaviors_by_ids(session, list(behavior_ids))}
        """
        get_behaviors_by_ids devuelve solo los que existen: si falta alguno, lo
        detecto acá y no recién en pleno partido con un KeyError dentro del tick
        """
        faltantes = behavior_ids - codes.keys()
        if faltantes:
            raise MatchInitializationError(f"No existen los comportamientos {sorted(faltantes)}.")
        """
         make_execute_behavior compila el codigo de cada comportamiento: un codigo
         sin on_tick (ValueError) o con errores de sintaxis/ejecución falla aca
        """
        execute_behavior = make_execute_behavior(codes)
    except Exception as exc:
        """
         aatrapo Exception (no solo MatchInitializationError) porque make_execute_behavior
         ejecuta código escrito por usuarios (exec): puede tirar ValueError (sin on_tick),
         SyntaxError, NameError, etc. Todos son "el partido no se puede preparar",
         un error del usuario y no un bug del servidor: se devuelve como 400
         "from exc" conserva el error original para los logs
        """
        raise InvalidConfigurationError(f"No se pudo preparar el partido: {exc}") from exc

    return state, execute_behavior
