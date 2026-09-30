"""
Schemas Pydantic para partidos amistosos
"""

from pydantic import BaseModel, ConfigDict

from src.models.match import MatchStatus


class FriendlyMatchOut(BaseModel):
    """
    Un partido de la lista, con los campos que define el contrato.
    """
    
    # from_attributes permite armar este schema directo desde un objeto Match de SQLAlchemy
    model_config = ConfigDict(from_attributes=True)

    match_id: int
    team_host_id: int
    team_away_id: int | None  # null mientras el partido no tiene visitante
    status: MatchStatus
    match_duration: int


class FriendlyListOut(BaseModel):
    """Respuesta 200 del contrato: {"matches": [...]}."""
    matches: list[FriendlyMatchOut]