"""
Rutas de comportamientos.

Igual que routes/players.py: solo traduce HTTP--dominio. La validación
vive en behavior_service y los errores los traduce el handler global de
AppError. get_current_user corre antes que todo, así que un token
inválido responde 401 aunque el query param también sea inválido.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from src.core.security import get_current_user
from src.database.base import get_db
from src.schemas.behavior import BehaviorResponse
from src.services.behavior_service import list_behaviors, get_behavior

router = APIRouter(prefix="/api/v1/behaviors", tags=["behaviors"])


@router.get("", response_model=list[BehaviorResponse], status_code=status.HTTP_200_OK)
def list_behaviors_endpoint(
    # Se recibe como texto (y no como bool) para que un valor inválido
    # devuelva 400 INVALID_QUERY_PARAMS, como dice el contrato, y no el
    # 422 genérico de FastAPI.
    is_default: str | None = Query(default=None),
    user_id: int = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[BehaviorResponse]:
    behaviors = list_behaviors(session, user_id=user_id, is_default=is_default)
    return [BehaviorResponse.model_validate(behavior) for behavior in behaviors]


@router.get("/{behavior_id}", response_model=BehaviorResponse, status_code=status.HTTP_200_OK)
def detail_behavior_endpoint(
    behavior_id: int,
    user_id: int = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> BehaviorResponse:
    behavior = get_behavior(session, user_id=user_id, behavior_id=behavior_id)
    return BehaviorResponse.model_validate(behavior)