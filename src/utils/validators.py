"""
Helpers de validación de formato, reutilizables por cualquier service o
endpoint.

A propósito son funciones puras (string -> bool), sin conocer HTTP, error
codes ni SQLAlchemy: quien las llama decide qué excepción lanzar.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

_ALLOWED_LOGO_EXTENSIONS = (".png", ".jpg", ".jpeg", ".svg")

# expresión regular para validar el Base64 (png, jpeg, svg+xml)
_BASE64_LOGO_RE = re.compile(r"^data:image/(png|jpeg|svg\+xml);base64,")


def is_valid_logo_format(logo: str) -> bool:
    """
    Válido si es una URL http(s) bien formada, si termina (ignorando un
    posible query string) con una extensión de imagen permitida, o si es
    un data URL base64 de imagen.
    """
    if not logo:
        return False

    parsed = urlparse(logo)
    looks_like_url = parsed.scheme in ("http", "https") and bool(parsed.netloc)
    has_allowed_extension = logo.lower().split("?")[0].endswith(_ALLOWED_LOGO_EXTENSIONS)

    # comprueba si coincide con el formato de Data URL base64
    is_base64_data = bool(_BASE64_LOGO_RE.match(logo))

    # actualiza el retorno para incluir la nueva validación
    return looks_like_url or has_allowed_extension or is_base64_data