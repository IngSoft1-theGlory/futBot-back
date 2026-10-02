
"""
Schemas Pydantic para la respuesta de POST /api/v1/live-token/global
"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr

class LiveTokenResponse(BaseModel):
    """
    Lo que devolvemos si la solicitud de token global sale bien (200 OK).
    """
    websocket_url: str 
    expires_in_seconds: int