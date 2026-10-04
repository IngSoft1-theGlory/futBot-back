"""
Schemas Pydantic de partidos amistosos
Definen la forma del JSON que entra (request) y el que sale (response)
"""

from __future__ import annotations

from pydantic import BaseModel
from pydantic import BaseModel, ConfigDict

from src.schemas.lineup_config import LineupConfig
from src.models.match import MatchStatus

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

# Representación de un partido individual dentro del listado de amistosos
class FriendlyMatchOut(BaseModel):
    # from_attributes permite armar este schema directo desde un objeto Match de SQLAlchemy
    model_config = ConfigDict(from_attributes=True)

    match_id: int
    team_host_id: int
    team_away_id: int | None  # null mientras el partido no tiene visitante
    status: MatchStatus
    match_duration: int

# Lo que devuelve el endpoint de listar amistosos (wrapper contenedor de la lista)
class FriendlyListOut(BaseModel):
    """Respuesta 200 del contrato: {"matches": [...]}."""
    matches: list[FriendlyMatchOut]

# Lo que el cliente manda en el body del POST de unirse a un amistoso
class JoinFriendlyRequest(LineupConfig):
    team_id: int
    # hereda formation_type, starting_players y substitute_players de LineupConfig


# Lo que el endpoint de unirse a un amistoso devuelve si todo sale bien.
class JoinFriendlyResponse(BaseModel):
    match_id: int
    team_host_id: int
    team_away_id: int
    status: str  # texto IN_PROGRESS, no el Enum
    match_duration: int


# Datos publicos de un equipo que se muestran en la sala de espera
class LobbyTeamOut(BaseModel):
    team_id: int
    team_name: str | None
    team_logo: str | None = None


# Lo que devuelve el endpoint de obtener el estado del lobby de un amistoso
class FriendlyLobbyResponse(BaseModel):
    match_id: int
    status: str  # texto PENDING o IN_PROGRESS, no el Enum
    match_duration: int
    team_host: LobbyTeamOut
    team_away: LobbyTeamOut | None  # null mientras el partido espera rival
