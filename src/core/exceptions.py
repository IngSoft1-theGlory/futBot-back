"""
Excepciones de dominio: subclases de AppError, traducidas a JSON por
un único handler global registrado en main.py.
"""

from __future__ import annotations
from fastapi import Request 
from fastapi.responses import JSONResponse

class AppError(Exception):
    """Error de negocio esperado (no un bug)"""
    
    status_code: int   # cada subclase concreta debe fijarlo — sin default
    error_code: str    # idem

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)

class BadRequestError(AppError):
    """Rama 400: la mayoría de los errores de validación de negocio
    caen acá. Las subclases (EmptyUsernameError, etc) solo pisan
    error_code, heredan este status_code."""
    status_code = 400
    error_code = "APP_ERROR"

class UnauthorizedError(AppError):
    """Rama 401: token ausente, inválido, expirado o mal firmado."""
    status_code = 401
    error_code = "UNAUTHORIZED"

class InvalidCredentialsError(AppError):
    """Rama 401 específica del login: email inexistente O contraseña
    incorrecta."""
    status_code = 401
    error_code = "INVALID_CREDENTIALS"

class ForbiddenError(AppError):
    """Rama 403: el usuario está autenticado pero no puede hacer esta acción."""
    status_code = 403
    error_code = "UNAUTHORIZED_ACTION"

class NotFoundError(AppError):
    """Rama 404: el recurso pedido no existe."""
    status_code = 404
    error_code = "NOT_FOUND"

class ConflictError(AppError):
    """Rama 409: el request choca con el estado actual del recurso."""
    status_code = 409
    error_code = "CONFLICT"

class UnprocessableError(AppError):
    """Rama 422 de negocio: el request está bien armado pero no se puede cumplir."""
    status_code = 422
    error_code = "APP_ERROR"

class PasswordIncorrectError(AppError):
    status_code = 401
    error_code = "PASSWORD_INCORRECT"

class InvalidSettingsError(BadRequestError):
    """Rama 400 INVALID_SETTINGS: la configuración del partido es inválida"""
    error_code = "INVALID_SETTINGS"

class InvalidConfigurationError(BadRequestError):
    """Rama 400 INVALID_CONFIGURATION: la formación o la alineación elegidas no son
    válidas (roles, jugadores o comportamientos que no corresponden)."""
    error_code = "INVALID_CONFIGURATION"

class PreconditionFailedError(UnprocessableError):
    """Rama 422 PRECONDITION_FAILED: el request está bien armado, pero el equipo
    no cumple un requisito previo (hoy, tener al menos 6 jugadores)."""
    error_code = "PRECONDITION_FAILED"

class MatchNotFoundError(NotFoundError):
    """ Rama 404 específica de partidos: el partido no existe"""
    error_code = "MATCH_NOT_FOUND"

class LeagueNotFoundError(NotFoundError):
    """ Rama 404 específica de ligas: la liga no existe"""
    error_code = "LEAGUE_NOT_FOUND"   

class MatchNotFinishedError(BadRequestError):
    """Rama 400 MATCH_NOT_FINISHED: el partido existe pero todavía no terminó,
    así que su resultado final aún no está disponible."""
    error_code = "MATCH_NOT_FINISHED"

class MatchUnavailableError(ConflictError):
    """Rama 409 MATCH_UNAVAILABLE: el partido ya empezó o ya tiene rival."""
    error_code = "MATCH_UNAVAILABLE"

class MatchPendingError(BadRequestError):
    """Rama 400 MATCH_PENDING: el partido todavía no empezó (espera rival)."""
    error_code = "MATCH_PENDING"

class MatchFinishedError(BadRequestError):
    """Rama 400 MATCH_FINISHED: el partido ya terminó."""
    error_code = "MATCH_FINISHED"

class LeagueNotPrivateError(BadRequestError):
    """Rama 400 LEAGUE_NOT_PRIVATE: la liga no es privada"""
    error_code = "LEAGUE_NOT_PRIVATE"

class InvalidLeagueCapacityError(BadRequestError):
    """Rama 400 INVALID_LEAGUE_CAPACITY: la capacidad elegida no es valida"""
    error_code = "INVALID_LEAGUE_CAPACITY"

class TeamNotInLeagueError(NotFoundError):
    """Rama 404 TEAM_NOT_IN_LEAGUE: el equipo no está inscripto en la liga."""
    error_code = "TEAM_NOT_IN_LEAGUE"

class HostCannotLeaveError(BadRequestError):
    """Rama 400 HOST_CANNOT_LEAVE: el anfitrión no puede abandonar su liga."""
    error_code = "HOST_CANNOT_LEAVE"

class LeagueAlreadyStartedError(ConflictError):
    """Rama 409 LEAGUE_ALREADY_STARTED: la liga ya no está en PENDING."""
    error_code = "LEAGUE_ALREADY_STARTED"

class InvalidQueryParamsError(BadRequestError):
    error_code = "INVALID_QUERY_PARAMS"

class BehaviorNotFoundError(NotFoundError):
    """ Rama 404 específica de comportamientos: el comportamiento no existe"""
    error_code = "BEHAVIOR_NOT_FOUND"

class InvalidData(BadRequestError):
    """ Rama 400 INVALID_DATA: datos invalidos para crear o actualizar comportamiento """
    error_code = "INVALID_DATA" 
    
class InvalidLineupError(InvalidConfigurationError):
    """Rama 400 INVALID_LINEUP: la formación o alineación para unirse a una liga no es válida."""
    error_code = "INVALID_LINEUP"

class LeagueUnavailableError(BadRequestError):
    """Rama 400 LEAGUE_UNAVAILABLE: la liga ya fue iniciada o terminó."""
    error_code = "LEAGUE_UNAVAILABLE"

class LeagueFullError(ConflictError):
    """Rama 409 LEAGUE_FULL: la liga alcanzó su cupo máximo de equipos."""
    error_code = "LEAGUE_FULL"

class AlreadyJoinedError(ConflictError):
    """Rama 409 ALREADY_JOINED: el equipo ya está inscripto en la liga."""
    error_code = "ALREADY_JOINED"

class JoinTokenRequiredError(ForbiddenError):
    """Rama 403 JOIN_TOKEN_REQUIRED: la liga es privada y no se envió join_token."""
    error_code = "JOIN_TOKEN_REQUIRED"

class JoinTokenExpiredError(ForbiddenError):
    """Rama 403 JOIN_TOKEN_EXPIRED: el join_token venció."""
    error_code = "JOIN_TOKEN_EXPIRED"

class InvalidJoinTokenError(ForbiddenError):
    """Rama 403 INVALID_JOIN_TOKEN: el join_token es inválido o es de otra liga u otro usuario."""
    error_code = "INVALID_JOIN_TOKEN"

class PlayerNotFoundError(NotFoundError): 
    """Rama 404 PLAYER_NOT_FOUND: el jugador no existe o es del equipo rival"""
    error_code = "PLAYER_NOT_FOUND"
    
class InsufficientTeamsError(BadRequestError):
    """Rama 400 INSUFFICIENT_TEAMS: no hay suficientes equipos para iniciar la liga."""
    error_code = "INSUFFICIENT_TEAMS"

class OddTeamsCountError(BadRequestError):
    """Rama 400 ODD_TEAMS_COUNT: hay un numero impar de equipos en la liga."""
    error_code = "ODD_TEAMS_COUNT"

class ResourceNotFoundError(NotFoundError):
    """Rama 404 RESOURCE_NOT_FOUND: el partido (en ejecución), el equipo o el jugador solicitado no existe."""
    error_code = "RESOURCE_NOT_FOUND"

class InvalidPlayerSelectionError(BadRequestError):
    """Rama 400 INVALID_PLAYER_SELECTION: el saliente no está en cancha o el entrante no está en el banco."""
    error_code = "INVALID_PLAYER_SELECTION"

class SubstitutionLimitExceededError(ConflictError):
    """Rama 409 SUBSTITUTION_LIMIT_EXCEEDED: el equipo ya hizo su cambio en esta pausa."""
    error_code = "SUBSTITUTION_LIMIT_EXCEEDED"
    
class LeagueNotInProgressError(ConflictError):
    """Rama 409 LEAGUE_NOT_IN_PROGRESS: la liga no está en curso."""
    error_code = "LEAGUE_NOT_IN_PROGRESS"

def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Función suelta, sin `app`: se registra en cualquier FastAPI() con
    add_exception_handler(AppError, app_error_handler)."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error_code, "message": exc.message},
    )