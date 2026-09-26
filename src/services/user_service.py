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
    y si algo falla, ROLLBACK completo.
    """

    if username is None or username.strip() == "":
        raise EmptyUsernameError("El nombre de usuario no puede estar vacío.")

    password_hash = hash_password(password)
    team_data = dict(team_data or {})

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

    except IntegrityError as exc:
        original_message = str(getattr(exc, "orig", exc))
        if _EMAIL_UNIQUE_CONSTRAINT in original_message or "email" in original_message.lower():
            raise DuplicateEmailError(f"El email '{email}' ya está en uso.") from exc
        raise

    return user