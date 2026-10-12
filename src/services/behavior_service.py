"""
Lógica de Behavior.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.core.exceptions import UnauthorizedError, InvalidQueryParamsError, BehaviorNotFoundError
from src.models.behavior import Behavior
from src.repositories.behavior_repository import list_behaviors_for_user, get_behavior_by_id
from src.repositories.user_repository import get_user_by_id


def parse_is_default(raw_value: str | None) -> bool | None:
    """
    Convierte el query param is_default ("true" / "false") a bool.
    Si no vino, devuelve None (sin filtro). Cualquier otro valor es 400,
    como pide el contrato (no 422 de validación genérica).
    """
    if raw_value is None:
        return None

    value = raw_value.strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False

    raise InvalidQueryParamsError("El parámetro 'is_default' debe ser un booleano válido.")


def list_behaviors(
    session: Session,
    *,
    user_id: int,
    is_default: str | None = None,
) -> list[Behavior]:
    """
    Devuelve los comportamientos disponibles para el usuario autenticado.

      1) Verifica que el usuario del token siga existiendo.
      2) Valida el filtro is_default.
      3) Consulta los comportamientos (lista vacía si no hay ninguno).
    """
    user = get_user_by_id(session, user_id)
    if user is None:
        # token válido de un usuario que ya no existe
        raise UnauthorizedError("El token de sesión no es válido o ha expirado")

    filter_is_default = parse_is_default(is_default)

    return list_behaviors_for_user(session, user_id, filter_is_default)


def get_behavior(session: Session, *, user_id: int, behavior_id: int) -> Behavior:
    """
    Devuelve los detalles del comportamiento seleccionado.

      1) Verifica que el usuario del token siga existiendo.
      2) Valida que el comportamiento exista.
      3) Consulta si el comportamiento es propio del usuario o si es default.
    """
    user = get_user_by_id(session, user_id)
    if user is None:
        # token válido de un usuario que ya no existe
        raise UnauthorizedError("El token de sesión no es válido o ha expirado")

    behavior = get_behavior_by_id(session, behavior_id)
    if behavior is None:
        raise BehaviorNotFoundError("El comportamiento seleccionado no existe")

    can_view = behavior.user_id == user_id or behavior.is_default
    if not can_view:
        raise BehaviorNotFoundError("El comportamiento seleccionado no existe")

    return behavior