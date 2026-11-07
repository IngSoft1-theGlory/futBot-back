"""
Schemas Pydantic para comportamientos.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from src.models.behavior import BehaviorType


class BehaviorResponse(BaseModel):
    """
    Respuesta de /api/v1/behaviors. Se usa en listar, ver detalle, crear y editar comportamientos.
    
    No expone user_id: el front solo necesita
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


class CreateUpdateBehaviorRequest(BaseModel):
    """Body de POST /behaviors (crear) y PUT /behaviors/{id} (editar)."""
    name: str 
    description: str 
    code: str
    behavior_type: BehaviorType