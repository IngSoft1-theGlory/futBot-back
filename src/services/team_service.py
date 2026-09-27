"""
Lógica y persistencia del equipo.

Validacion de los atributos del equipo y la relacion de con el usuario.
"""

from __future__ import annotations

from sqlalchemy.orm import Session
from src.models.team import Team
from src.repositories.team_repository import get_team_by_user_id

_ALLOWED_LOGO_EXTENSIONS = (".png", ".jpg", ".jpeg", ".svg")

class UserAlreadyHasTeamError(ValueError):
    """El usuario ya posee un equipo asignado (USER_ALREADY_HAS_TEAM)"""

class VoidTeamNameError(ValueError):
    """El nombre del equipo no puuede estra vacio (VOID_TEAM_NAME)"""

class VoidTeamLogoError(ValueError):
    """El logo del equipo no puede estar vacio (VOID_TEAM_LOGO)"""

class InvalidFormatLogoError(ValueError):
    """El logo proporcionado tiene un formato invalido(INVALID_FORMAD_LOGO)"""

def validate_team_logo(team_logo: str) -> None:
    """
    Valida que el logo no sea nulo/vacío y sea una URL válida o una imagen (.png, .jpg, .jpeg, .svg).
    """
    if team_logo is None or team_logo.strip() == "":
        raise VoidTeamLogoError("El logo del equipo no puede estar vacío.")

    logo_clean = team_logo.strip().lower()
    is_url = logo_clean.startswith(("http://", "https://"))
    has_valid_extension = any(
        logo_clean.split("?")[0].endswith(ext) for ext in _ALLOWED_LOGO_EXTENSIONS
    )

    if not (is_url or has_valid_extension):
        raise InvalidFormatLogoError(
            "El logo del equipo debe ser una URL válida (http/https) "
            "o poseer una extensión permitida (.png, .jpg, .jpeg, .svg)."
        )

def validate_user_has_no_team(session: Session, user_id: int) -> None:
    """
    Verifica que el usuario no posea un equipo
    """
    existing_team = get_team_by_user_id(session, user_id)
    if existing_team is not None:
        raise UserAlreadyHasTeamError("El usuario ya posee un equipo creado.")

def create_team_with_user(
    session: Session,
    *,
    user_id: str,
    team_name: str,
    team_logo: str,
) -> Team:
    """
    Crea un User y su Team asociado en una única transacción atómica.
    y si algo falla, ROLLBACK completo.
    """

    if team_name is None or team_name.strip() == "":
        raise VoidTeamNameError("El nombre del equipo no puede estar vacío.")

    validate_team_logo(team_logo)
    """
    En esta funcion de validacion contempla los casos de 
    logo como logo vacio y logo con formato invalido
    """

    validate_user_has_no_team(session, user_id)

    team = Team(
        user_id = user_id,
        team_name = team_name,
        team_logo = team_logo,
    )

    session.add(team)
    session.commit()
    session.refresh(team)

    return team