""" 
Logica de negocio para la entidad League.
"""

from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy import delete, select
from src.core.exceptions import (
    AlreadyJoinedError,
    HostCannotLeaveError,
    InvalidConfigurationError,
    InvalidLeagueCapacityError,
    InvalidLineupError,
    InvalidQueryParamsError,
    JoinTokenRequiredError,
    LeagueAlreadyStartedError,
    LeagueFullError,
    LeagueNotFoundError,
    ForbiddenError,
    LeagueNotPrivateError,
    LeagueUnavailableError,
    NotFoundError,
    PasswordIncorrectError,
    TeamNotInLeagueError,
    InsufficientTeamsError,
    OddTeamsCountError,
    NotLeagueHostError,
)

from src.schemas.league import (
    CreateLeagueRequest, 
    LeagueOut, 
    LeagueDetailOut, 
    LeagueTeamOut, 
    JoinLeagueRequest, 
    FixtureMatchOut, 
    FixtureTeamOut, 
    FixtureScoreOut
)

from src.models.league import League, LeagueStatus
from src.repositories.league_repository import get_leagues, get_league_by_id, get_league_teams, is_team_in_league
from src.repositories.user_repository import get_user_by_id
from src.repositories.match_repository import get_league_fixture, get_finished_league_matches
from src.core.security import hash_password, verify_join_token, verify_password
from src.models.lineup_entry import LineupEntry
from src.services.standings_service import build_standings
from src.services.fixture_service import generate_fixture
from src.services.lineup_service import (
    save_lineup,
    validate_team_belongs_to_user,
    validate_match_duration,
    validate_min_players, 
    validate_lineup,
)

MIN_TEAMS_TO_START = 4  # cantidad mínima de equipos para iniciar una liga

def create_league(session: Session, user_id: int, payload: CreateLeagueRequest) -> League: 
    """llama a las validaciones y, si todas pasan, guarda la League y las 6 LineupEntry en una sola transaccion"""

    validate_team_belongs_to_user(session, user_id, payload.team_id)
    validate_match_duration(payload.match_duration)
    validate_league_capacity(payload.max_teams)
    team_players = validate_min_players(session, payload.team_id)
    validate_lineup(session, payload, team_players, user_id)
    
    password_hash = hash_password(payload.password) if payload.password else None 

    try:
        # la liga y los 6 lineup entries se crean aca: si uno falla,
        # tiene que eliminarse todo (rollback) y no quedar nada guardado en la DB.

        # le paso a liga los param necesarios para crear una liga
        league = League(
            league_name = payload.league_name,
            max_teams = payload.max_teams,
            password_hash = password_hash, 
            host_team_id=payload.team_id,
            match_duration=payload.match_duration,
            status=LeagueStatus.PENDING,
            penalties_enabled=payload.penalties_enabled
        )

        session.add(league)
        session.flush()  # guarda la liga para conseguirle su id, pero todavía se puede deshacer

        # guardo la alineación del anfitrión en la DB 
        save_lineup(session, None, payload.team_id, payload, league.league_id)

        session.commit()  # recién acá queda guardado de verdad (liga y lineup entries)

    except Exception:
        session.rollback()  # deshace todo lo de este intento, liga incluida
        raise

    return league


def validate_league_capacity(max_teams: int) -> None: 
    if max_teams not in (4, 6, 8, 10, 12):
        raise InvalidLeagueCapacityError ("El cupo máximo de la liga debe ser un número par entre 4 y 12")


def list_leagues(session: Session, page: str | None, limit: str | None, status: str | None) -> list[LeagueOut]:
    """ 
    obtiene un listado de ligas, filtradas por status y paginadas por page y limit.
    Valida los parametros de entrada y lanza InvalidQueryParamsError si alguno es invalido
    """
    # Validacion de page y limit: si no son enteros positivos, 
    # lanza InvalidQueryParamsError
    if page is None:
        page_int = 1
    else:
        try:
            page_int = int(page)
        except ValueError:
            raise InvalidQueryParamsError("page debe ser un entero positivo.") from None
        if page_int < 1:
            raise InvalidQueryParamsError("page debe ser un entero positivo.")

    if limit is None:
        limit_int = 20
    else:
        try:
            limit_int = int(limit)
        except ValueError:
            raise InvalidQueryParamsError("limit debe ser un entero positivo.") from None
        if limit_int < 1:
            raise InvalidQueryParamsError("limit debe ser un entero positivo.")
        if limit_int > 100:
            raise InvalidQueryParamsError("limit no puede ser mayor a 100.")

    # Validacion de status: si no es None, intentar convertirlo a LeagueStatus; 
    # si falla, lanza InvalidQueryParamsError
    if status is None: # Si no se envia un estado, se mantiene None y devuelve todas las ligas
        status_enum = None
    else:
        try:
            status_enum = LeagueStatus(status)
        except ValueError:
            # Se lanza InvalidQueryParamsError con un mensaje que indica los valores válidos de status
            raise InvalidQueryParamsError(
                f"status debe ser uno de {', '.join(s.value for s in LeagueStatus)}."
                ) from None

    # Se obtienen las ligas  de la base de datos filtrados y validados.
    rows = get_leagues(
        session,
        status=status_enum,
        page=page_int,
        limit=limit_int,
    )

    # Se construye la lista de ligas a devolver, con el formato requerido por LeagueOut
    result = []
    for league, team_count in rows:
        result.append(
            LeagueOut(
                league_id=league.league_id,
                league_name=league.league_name,
                max_teams=league.max_teams,
                current_teams_count=team_count,
                status=league.status,
                # si tiene password_hash, es privada; si no, es pública. El hash nunca sale del service.
                is_private=league.password_hash is not None,
            )
        )
        
    return result  

def check_league_password(session: Session, league_id: int, password: str) -> None:
    league = session.get(League, league_id)

    if league is None: 
        raise LeagueNotFoundError("La liga no fue encontrada")

    if league.password_hash is None: 
        raise LeagueNotPrivateError("La liga que se está intentando verificar no es privada")

    if not(verify_password(password, league.password_hash)):
        raise PasswordIncorrectError("La contraseña ingresada no es correcta")


def get_league_detail(session: Session, user_id: int, league_id: int) -> LeagueDetailOut:
    """
    Devuelve el detalle de una liga en cualquier estado (lobby o liga iniciada).
    404 LEAGUE_NOT_FOUND si no existe; 403 UNAUTHORIZED_ACTION si es privada
    y el equipo del usuario no esta inscripto.
    """
    league = get_league_by_id(session, league_id)
    if league is None:
        raise LeagueNotFoundError("No existe la liga con el ID especificado.")

    teams = get_league_teams(session, league_id)
    is_private = league.password_hash is not None

    # una liga privada solo la pueden ver los equipos inscriptos
    if is_private:
        user = get_user_by_id(session, user_id)
        if user is None or all(team.team_id != user.team_id for team in teams):
            raise ForbiddenError("No se permite ver el estado de esta liga")

    # Se obtiene el fixture de la liga, ordenado por fecha, con los datos de los equipos y el resultado de cada partido
    partidos = get_league_fixture(session, league_id)
    fixture = [
        FixtureMatchOut(
            match_id=partido.match_id,
            # se agrega el numero de fecha y el estado del partido, que puede ser PENDING, IN_PROGRESS o FINISHED
            round_number=partido.round_number,
            status=partido.status,
            # Se agregan los datos de los equipos y el resultado del partido
            team_host=FixtureTeamOut(team_id=partido.host_team.team_id, team_name=partido.host_team.team_name),
            team_away=FixtureTeamOut(team_id=partido.away_team.team_id, team_name=partido.away_team.team_name),
            # Se agregan los goles de cada equipo, si el partido no se jugó, los goles son 0
            score=FixtureScoreOut(home=partido.home_goals, away=partido.away_goals, phome=partido.home_penalty_goals, paway=partido.away_penalty_goals),
        )
        for partido in partidos     
    ]

    # Si la liga ya empezó, se calculan los puntos de cada equipo y se ordena por puntos, diferencia de goles y goles a favor
    ranking = []
    if league.status != LeagueStatus.PENDING:
        ranking = build_standings(teams, get_finished_league_matches(session, league_id))

    return LeagueDetailOut(
        league_id=league.league_id,
        league_name=league.league_name,
        status=league.status,
        is_private=is_private,
        host_team_id=league.host_team_id,
        max_teams=league.max_teams,
        current_teams_count=len(teams),
        match_duration=league.match_duration,
        teams=[LeagueTeamOut(team_id=team.team_id, team_name=team.team_name) for team in teams],
        fixture=fixture,    
        ranking=ranking,
        penalties_enabled=league.penalties_enabled
    )


def join_league(session: Session, user_id: int, league_id: int, payload: JoinLeagueRequest) -> League:
    """Inscribe al equipo en la liga y guarda su alineación en una sola transacción."""

    validate_team_belongs_to_user(session, user_id, payload.team_id)

    # with_for_update bloquea la fila de la liga para que dos inscripciones simultáneas no superen el cupo
    league = session.scalars(select(League).where(League.league_id == league_id).with_for_update()).first()
    if league is None:
        raise NotFoundError("La liga no existe")
    if league.status != LeagueStatus.PENDING:
        raise LeagueUnavailableError("La liga ya fue iniciada")

    if league.password_hash is not None:
        if payload.join_token is None:
            raise JoinTokenRequiredError("La liga es privada, se requiere un token de unión")
        verify_join_token(payload.join_token, user_id, league_id)

    # un equipo está inscripto si tiene lineup_entries en la liga
    enrolled_team_ids = set(session.scalars(
        select(LineupEntry.team_id).where(LineupEntry.league_id == league_id).distinct()
    ))
    if payload.team_id in enrolled_team_ids:
        raise AlreadyJoinedError("El equipo ya está inscripto en la liga")
    if len(enrolled_team_ids) >= league.max_teams:
        raise LeagueFullError("La liga alcanzó su cupo máximo de equipos")

    team_players = validate_min_players(session, payload.team_id)
    try:
        validate_lineup(session, payload, team_players, user_id)
    except InvalidConfigurationError as error:
        raise InvalidLineupError(error.message)

    try:
        save_lineup(session, None, payload.team_id, payload, league_id)
        # envía temporalmente los cambios a la BD, el commit los confirma despues
        session.flush() 
        # enrolled_team_ids son los equipos inscriptos, sin contar el actual que se esta agregando
        if len(enrolled_team_ids) + 1 == league.max_teams:
            # si el equipo que se acaba de inscribir completa el cupo, se inicia la liga
            _start_league(session, league)
        session.commit()
    except Exception:
        session.rollback()
        raise

    return league

def exit_league(
        session: Session, 
        user_id: int, 
        league_id: int, 
        team_id: int
) -> None:
    """ 
    Saca al equipo de la liga borrando sus 6 filas de lineup_entries,
    en un orden de las validaciones.
    """
    # Se obtiene la liga con el id y se bloquea la fila para update,
    # Si no existe la liga, lanza LeagueNotFoundError 404
    league = get_league_by_id(session, league_id, for_update=True)
    if league is None:
        raise LeagueNotFoundError("No existe una liga con el ID especificado.")

    # Se valida que el equipo pertenece al usuario, si no, lanza una excepcion
    validate_team_belongs_to_user(session, user_id, team_id)

    # Se valida que el equipo esta inscripto en la liga, 
    # si no lanza TeamNotInLeagueError 404
    if not is_team_in_league(session, league_id, team_id):
        raise TeamNotInLeagueError("El equipo no está inscripto en la liga.")

    # Si el equipo es el anfitrion de la liga, no puede abandonarla
    if league.host_team_id == team_id:
        raise HostCannotLeaveError("El anfitrión no puede abandonar su liga.")

    # Si la liga ya empezó, no se puede abandonar - 409 LEAGUE_ALREADY_STARTED
    if league.status != LeagueStatus.PENDING:
        raise LeagueAlreadyStartedError(
            "La liga ya no está en estado PENDING, no se puede abandonar.")

    # Si sale todo bien, se borran las filas de LineupEntry y se hace commit
    # si hay un error se hace rollback y se lanza la excepcion
    try:
        delete_stmt = delete(LineupEntry).where(
            LineupEntry.league_id == league_id,
            LineupEntry.team_id == team_id
        )
        session.execute(delete_stmt)
        session.commit()
    except Exception:
        session.rollback()
        raise

def _start_league(session: Session, league: League) -> None:
    """
    Inicia una liga pendiente y genera sus partidos,
    esta funcion se utiliza tanto cuando el anfitrion inicia la liga
    manualmente como cuando se inicia de forma automática,
    no se guardan (commit) los cambios en la base de datos.
    """
    
    # si la liga no está en estado PENDING, significa que ya ha sido iniciada y no se puede iniciar de nuevo, 
    # por lo tanto, se lanza una excepción LeagueAlreadyStartedError con un mensaje adecuado.
    if league.status != LeagueStatus.PENDING:
        raise LeagueAlreadyStartedError("La liga ya fue iniciada y no se puede iniciar de nuevo.")
    
    # la lista de equipos insccriptos
    teams = get_league_teams(session, league.league_id)

    # si la cantidad de equipos es menor a la cantidad mínima o 
    # si la cantidad es impar, se lanza una excepción.
    if len(teams) < MIN_TEAMS_TO_START :
        raise InsufficientTeamsError(
            f"La liga necesita al menos {MIN_TEAMS_TO_START} equipos para iniciarse"
        )
        
    if len(teams) % 2 != 0:
        raise OddTeamsCountError("La liga tiene un numero impar de equipos, no se puede iniciar.")

    # se cambia el estado de la liga a IN_PROGRESS
    league.status = LeagueStatus.IN_PROGRESS
 
    # se genera el fixture de la liga, que crea los partidos y los guarda en la base de datos
    generate_fixture(session, league)


def start_league(session: Session, user_id: int, league_id: int) -> League:
    """  
    Inicia una liga pendiente,
    verifica que la liga exista, que el usuario sea el anfitrión y que cumpla los 
    requisitos para arrancar. Si todo esta bien se genera el fixture 
    y se guarda la liga con estado IN_PROGRESS.
    """

    # se obtiene la liga con el id  y se bloquea operacion, si no existe se lanza 
    # LeagueNotFoundError (En for_update bloquea la fila mientras la operacion esta abierta,
    #  para que no se pueda iniciar la liga dos veces al mismo tiempo)
    league = get_league_by_id(session, league_id, for_update=True)
    if league is None:
        raise LeagueNotFoundError("No existe una liga con el ID especificado.")
    
    # Se obtiene el usuario con el id especificado y se valida que sea el anfitrión de la liga
    user = get_user_by_id(session, user_id)
    if user is None or user.team_id != league.host_team_id:
        raise ForbiddenError("El usuario no es el anfitrión de la liga y no puede iniciarla")
    
    # Se intenta iniciar la liga y generar los partidos, 
    # si hay un error se hace rollback y se lanza la excepción
    try: 
        _start_league(session, league)
         # si sale bien la creacion de partido se guarda la liga con el estado IN_PROGRESS
        session.commit()
    except Exception:
        session.rollback()
        raise

    return league

def cancel_league(session: Session, user_id: int, league_id: int) -> None: 
    """
    Cancela una liga pendiente, borrando la liga y sus lineup_entries. 
    Solo el anfitrion puede cancelar la liga
    """

    league = get_league_by_id(session, league_id, for_update=True)

    if league is None: 
        raise LeagueNotFoundError("No existe una liga con el ID especificado.")

    user = get_user_by_id(session, user_id)
    if user is None or user.team_id != league.host_team_id:
        raise NotLeagueHostError("Sólo el anfitrión puede eliminar la liga")    
    
    if league.status != LeagueStatus.PENDING:
        raise LeagueAlreadyStartedError("No se puede eliminar una liga que ya fue iniciada")

    try:
        # delete() marca la liga para borrarse, sin hacer commit
        session.delete(league)   # Las lineup_entries se borran solas por el on delete cascade de la FK
        session.commit() 
    except Exception:
        session.rollback()
        raise