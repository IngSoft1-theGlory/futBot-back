"""
Consultas de persistencia sobre Behavior.
Sólo lectura.
"""

from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from src.models.behavior import Behavior


def list_behaviors_for_user(
    session: Session, user_id: int, is_default: bool | None = None
) -> list[Behavior]:
    """
    Comportamientos disponibles para un usuario:
      - is_default=None  -> los predeterminados del sistema + los personalizados del usuario
      - is_default=True  -> solo los predeterminados
      - is_default=False -> solo los personalizados del usuario

    Nunca devuelve comportamientos personalizados de otros usuarios.
    """
    defaults = Behavior.is_default.is_(True)
    own = and_(Behavior.is_default.is_(False), Behavior.user_id == user_id)

    if is_default is True:
        condition = defaults
    elif is_default is False:
        condition = own
    else:
        condition = or_(defaults, own)

    # Primero los predeterminados y después los personalizados, cada grupo
    # en orden de creación, para que el orden sea siempre el mismo.
    statement = (
        select(Behavior)
        .where(condition)
        .order_by(Behavior.is_default.desc(), Behavior.behavior_id)
    )
    return list(session.scalars(statement).all())


def get_behavior_by_id(session: Session, behavior_id: int) -> Behavior | None:
    return session.get(Behavior, behavior_id)