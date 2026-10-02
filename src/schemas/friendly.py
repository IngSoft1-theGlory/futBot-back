"""
Schemas Pydantic de partidos amistosos
Definen la forma del JSON que entra (request) y el que sale (response)
"""

from __future__ import annotations

from pydantic import BaseModel
from src.schemas.lineup_config import LineupConfig

# Lo que el cliente manda en el body del POST de crear amistoso 
class CreateFriendlyRequest(LineupConfig):
    team_id: int
    match_duration: int 
    # hereda formation_type, starting_players y substitute_players de LineupConfig 


# Lo que el endpoint de crear amistoso devuelve si todo sale bien.
class CreateFriendlyResponse(BaseModel):
    match_id: int
    team_host_id: int
    status: str # texto PENDING, no el Enum 
    match_duration: int