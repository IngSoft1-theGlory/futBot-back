"""
Schemas Pydantic para comportamientos.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class BehaviorResponse(BaseModel):
    """
    Un comportamiento tal como lo devuelve la API (ver contrato:
    GET /api/v1/behaviors). No expone user_id: el front solo necesita
    saber si es predeterminado o personalizado (is_default).
    """

    # from_attributes permite armar el schema directo desde el modelo
    # de SQLAlchemy: BehaviorResponse.model_validate(behavior)
    model_config = ConfigDict(from_attributes=True)

    behavior_id: int
    name: str
    description: str
    code: str
    is_default: bool