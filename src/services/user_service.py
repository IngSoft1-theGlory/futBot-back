"""
Lógica de persistencia de User, incluyendo 

operación transaccional User + Team.
"""

from __future__ import annotations

from typing import Any
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from src.core.security import hash_password
from src.models.team import Team
from src.models.user import User
from src.services.team_service import validate_team_logo, validate_team_name

# Nombre del constraint UNIQUE de la columna email (ver NAMING_CONVENTION en
# database/base.py). Se usa para distinguir "email duplicado" de cualquier
# otro IntegrityError que pueda tirar la DB.
_EMAIL_UNIQUE_CONSTRAINT = "uq_users_email"

class EmptyUsernameError(ValueError):
    """El username es vacío (o sólo espacios)."""

class DuplicateEmailError(ValueError):
    """El email ya pertenece a otro usuario."""

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
    Si algo falla, ROLLBACK completo (ni user ni team quedan persistidos).
    """

    if username is None or username.strip() == "":
        raise EmptyUsernameError("El nombre de usuario no puede estar vacío.")

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