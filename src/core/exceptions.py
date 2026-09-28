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


def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Función suelta, sin `app`: se registra en cualquier FastAPI() con
    add_exception_handler(AppError, app_error_handler)."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error_code, "message": exc.message},
    )