"""
Lógica de persistencia de User, incluyendo la operación transaccional
User + Team.

El desarrollador de POST /api/v1/auth/register solo necesita llamar a
create_user_with_team(...): todas las reglas del contrato (VOID_USERNAME,
INVALID_FORMAT, VOID_TEAM_NAME, VOID_TEAM_LOGO, INVALID_LOGO_FORMAT,
DUPLICATE_EMAIL) se validan acá y se señalizan con una excepción propia.
La ruta no valida nada: solo llama a esta función y deja que el exception
handler global (ver src/core/exceptions.py y src/main.py) traduzca
cualquiera de estas excepciones a la respuesta HTTP del contrato.

Orden de validación (todas antes de tocar la DB, salvo el email duplicado
que depende de la constraint UNIQUE): username -> formato de email ->
team_name -> team_logo (vacío) -> team_logo (formato). Fail fast con lo
más barato primero.
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

    password_hash = hash_password(password)

    try:
        with session.begin():
            team = Team(**team_data)
            session.add(team)
            session.flush()

            user = User(
                username=username,
                email=email,
                password_hash=password_hash,
                team_id=team.team_id,
            )
            session.add(user)
            session.flush()
        # Sale del `with` sin excepción -> COMMIT. Con excepción,
        # session.begin() ya hizo ROLLBACK y la vuelve a lanzar.
    except IntegrityError as exc:
        original_message = str(getattr(exc, "orig", exc))
        if _EMAIL_UNIQUE_CONSTRAINT in original_message or "email" in original_message.lower():
            raise DuplicateEmailError(f"El email '{email}' ya está en uso.") from exc
        raise

    return user