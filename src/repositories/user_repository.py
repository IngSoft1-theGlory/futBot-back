"""
Consultas de persistencia sobre User.
Sólo lectura: la escritura vive en src/services/user_service.py.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from src.models.user import User

""" Obtener un usuario con id """ 
def get_user_by_id(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)

""" Obtener un usuario por email """
def get_user_by_email(session: Session, email: str) -> User | None:
    # Obtener el usuario que posea el mismo email proporcionado.
    statement = select(User).where(User.email == email.strip().lower())
    return session.scalars(statement).first()