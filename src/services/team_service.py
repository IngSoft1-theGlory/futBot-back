"""
Validaciones de negocio del equipo, mapeadas a los errores del contrato.
No conoce nada sobre User.
"""

from __future__ import annotations

from src.utils.validators import is_valid_logo_format


class VoidTeamNameError(ValueError):
    """El nombre del equipo no puede estar vacío (VOID_TEAM_NAME)"""


class VoidTeamLogoError(ValueError):
    """El logo del equipo no puede estar vacío (VOID_TEAM_LOGO)"""


class InvalidLogoFormatError(ValueError):
    """El logo proporcionado tiene un formato inválido (INVALID_LOGO_FORMAT)"""


def validate_team_name(team_name: str) -> None:
    if team_name is None or team_name.strip() == "":
        raise VoidTeamNameError(
            "El nombre del equipo no puede quedar vacío o contener sólo espacios."
        )

# chequea que el logo tenga un formato valido
def validate_team_logo(team_logo: str) -> None:
    if team_logo is None or team_logo.strip() == "":
        raise VoidTeamLogoError("El logo del equipo no puede estar vacío.")

    if not is_valid_logo_format(team_logo):
        raise InvalidLogoFormatError(
            "El logo del equipo debe ser una URL válida (http/https), "
            "un string base64 de imagen, o poseer una extensión permitida "
            "(.png, .jpg, .jpeg, .svg)."
        )