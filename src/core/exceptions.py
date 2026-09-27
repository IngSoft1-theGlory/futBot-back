"""
Excepciones de dominio y su traducción a códigos HTTP.

Las reglas de negocio (email duplicado, campos vacíos, formatos inválidos,
etc.) se validan en la capa de servicio (`src/services/`) lanzando una
subclase de `AppError`. La ruta HTTP no hace `try/except` por cada regla:
un único exception handler global, registrado en `src/main.py`, traduce
cualquier `AppError` a la respuesta `{"error": ..., "message": ...}` que
exige el contrato de API, usando el `status_code` y `error_code` que cada
subclase declara.

Cualquier endpoint futuro que necesite un nuevo error de negocio solo
define una subclase (acá o junto a su propio service); no hace falta
tocar el handler global ni las rutas existentes.
"""

from __future__ import annotations


class AppError(Exception):
    """Error de negocio esperado (no un bug): sabemos qué HTTP status y
    qué error_code de contrato le corresponde."""

    status_code: int = 400
    error_code: str = "APP_ERROR"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)