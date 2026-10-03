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
    """Rama 404 MATCH_NOT_FOUND: el partido no existe o fue cancelado."""
    error_code = "MATCH_NOT_FOUND"

class MatchUnavailableError(ConflictError):
    """Rama 409 MATCH_UNAVAILABLE: el partido ya empezó o ya tiene rival."""
    error_code = "MATCH_UNAVAILABLE"

def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Función suelta, sin `app`: se registra en cualquier FastAPI() con
    add_exception_handler(AppError, app_error_handler)."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error_code, "message": exc.message},
    )