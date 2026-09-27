"""
Helpers de validación de formato, reutilizables por cualquier service o
endpoint.

A propósito son funciones puras (string -> bool), sin conocer HTTP, error
codes ni SQLAlchemy: quien las llama decide qué excepción lanzar.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_ALLOWED_LOGO_EXTENSIONS = (".png", ".jpg", ".jpeg", ".svg")

# NUEVO: Agregamos la expresión regular para validar el Base64 (png, jpeg, svg+xml)
_BASE64_LOGO_RE = re.compile(r"^data:image/(png|jpeg|svg\+xml);base64,")


def is_valid_email_format(email: str) -> bool:
    """Formato básico (no verifica que el dominio exista de verdad)."""
    return bool(_EMAIL_RE.match(email or ""))


def is_valid_logo_format(logo: str) -> bool:
    """
    Válido si es una URL http(s) bien formada, si termina con una
    extensión de imagen permitida, o si es un string base64 de imagen válido.
    """
    if not logo:
        return False

    parsed = urlparse(logo)
    looks_like_url = parsed.scheme in ("http", "https") and bool(parsed.netloc)
    has_allowed_extension = logo.lower().endswith(_ALLOWED_LOGO_EXTENSIONS)
    
    # NUEVO: Comprobamos si coincide con el formato de Data URL base64
    is_base64_data = bool(_BASE64_LOGO_RE.match(logo))

    # Actualizamos el retorno para incluir la nueva validación
    return looks_like_url or has_allowed_extension or is_base64_data