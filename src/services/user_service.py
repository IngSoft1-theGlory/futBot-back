"""
Lógica de persistencia de User, incluyendo 

operación transaccional User + Team.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.exceptions import AppError
from src.core.security import hash_password
from src.models.team import Team
from src.models.user import User
from src.utils.validators import is_valid_email_format, is_valid_logo_format
from src.services.team_service import validate_team_logo, validate_team_name

_EMAIL_UNIQUE_CONSTRAINT = "uq_users_email"


class EmptyUsernameError(AppError):
    error_code = "VOID_USERNAME"


class InvalidEmailFormatError(AppError):
    error_code = "INVALID_FORMAT"


class DuplicateEmailError(AppError):
    error_code = "DUPLICATE_EMAIL"


class EmptyTeamNameError(AppError):
    error_code = "VOID_TEAM_NAME"


class EmptyTeamLogoError(AppError):
    error_code = "VOID_TEAM_LOGO"


class InvalidLogoFormatError(AppError):
    error_code = "INVALID_LOGO_FORMAT"


def create_user_with_team(
    session: Session,
    *,
    username: str,
    email: str,
    password: str,
    team_data: dict[str, Any] | None = None,
) -> User:
    """
    Crea un User y su Team asociado en una única transacción atómica.

      1. Valida username, email, team_name, team_logo (sin tocar la DB).
      2. Hashea la contraseña.
      3. Crea el Team.
      4. Crea el User asociado a ese Team.
      5. Confirma todo junto; si algo falla, ROLLBACK completo.
    """
    team_data = dict(team_data or {})
    team_name = team_data.get("name")
    team_logo = team_data.get("logo")

    if username is None or username.strip() == "":
        raise EmptyUsernameError("El nombre de usuario no puede estar vacío.")

    if not is_valid_email_format(email):
        raise InvalidEmailFormatError("El email ingresado no tiene un formato válido.")

    if team_name is None or team_name.strip() == "":
        raise EmptyTeamNameError("El nombre del equipo no puede quedar vacío.")

    if team_logo is None or team_logo.strip() == "":
        raise EmptyTeamLogoError("Debes proporcionar un logo para el equipo.")

    if not is_valid_logo_format(team_logo):
        raise InvalidLogoFormatError(
            "El logo ingresado debe ser una URL válida o tener un formato de "
            "imagen permitido (.png, .jpg, .jpeg, .svg)."
        )
    username = username.strip()
    email = "" if email is None else email.strip().lower()  # "Juan@X.com" y "juan@x.com" cuentan como el mismo email

    team_data = dict(team_data or {})

    # validamos el team antes de tocar la db o hashear la password
    validate_team_name(team_data.get("team_name"))
    validate_team_logo(team_data.get("team_logo"))

    password_hash = hash_password(password)

    try:
        # el team y el user se crean los dos acá adentro: si uno falla,
        # tiene que desaparecer el otro también
        team = Team(**team_data)
        session.add(team)
        session.flush()  # guarda el team para conseguirle su id, pero todavía se puede deshacer

        user = User(
            username=username,
            email=email,
            password_hash=password_hash,
            team_id=team.team_id,
        )
        session.add(user)
        session.flush() 

        session.commit()  # recien aca queda guardado de verdad (user y team)

    except IntegrityError as exc:
        session.rollback() # borra todo lo que se hizo en este intento, team incluido
        original_message = str(getattr(exc, "orig", exc))
        if _EMAIL_UNIQUE_CONSTRAINT in original_message or "email" in original_message.lower():
            raise DuplicateEmailError(f"El email '{email}' ya está en uso.") from exc
        raise
    except Exception:
        session.rollback()  # cualquier otro problema tambien deshace todo
        raise

    return user