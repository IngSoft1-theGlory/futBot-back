"""
Consultas de persistencia sobre User.
Sólo lectura: la escritura vive en app/services/user_service.py.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.user import User


def get_user_by_id(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def get_user_by_email(session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    return session.scalars(statement).first()