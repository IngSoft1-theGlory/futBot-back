"""
Schemas Pydantic para jugadores (creación).
"""

from __future__ import annotations

from pydantic import BaseModel, StrictInt


class CreatePlayerRequest(BaseModel):
    """
    Body de POST /api/v1/players. StrictInt rechaza "50", 50.5 y true con
    422 antes de llegar al service. Si el body trae team_id (u otro campo
    extra) se ignora: el equipo sale siempre del usuario autenticado.
    """
    name: str
    number: StrictInt
    power: StrictInt
    agility: StrictInt
    control: StrictInt
    speed: StrictInt
    strength: StrictInt


class PlayerResponse(BaseModel):
    player_id: int
    name: str
    number: int
    power: int
    agility: int
    control: int
    speed: int
    strength: int
