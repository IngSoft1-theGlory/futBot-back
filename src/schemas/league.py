""" 
Schemas pydantic de ligas
Definen la forma del JSON que entra (request) y el que sale (response)
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.models.league import LeagueStatus
from src.schemas.lineup_config import LineupConfig


class CreateLeagueRequest(LineupConfig):
    league_name: str
    match_duration: int 
    max_teams: int 
    password: str | None = None # si no viene, es None 
    team_id: int 
    # hereda formation_type, starting_players y substitute_players de LineupConfig 

class CreateLeagueResponse(BaseModel): 
    league_id: int 
    league_name: str 
    status: str 
    is_private: bool 
    match_duration: int 
    max_teams: int 
    current_teams_count: int 
    host_team_id: int

class LeagueOut(BaseModel):
    league_id: int
    league_name: str
    max_teams: int
    current_teams_count: int
    status: LeagueStatus
    is_private: bool

class LeagueListOut(BaseModel):
    leagues: list[LeagueOut]
    
class VerifyPasswordRequest(BaseModel):
    password: str

class VerifyPasswordResponse(BaseModel):
    join_token: str
    expires_in_seconds: int


class LeagueTeamOut(BaseModel):
    team_id: int
    team_name: str


class LeagueDetailOut(BaseModel):
    """Respuesta de GET /api/v1/leagues/{leagueId}: sirve para el lobby y para la liga iniciada."""
    league_id: int
    league_name: str
    status: LeagueStatus
    is_private: bool
    host_team_id: int
    max_teams: int
    current_teams_count: int
    match_duration: int
    teams: list[LeagueTeamOut]
    # por ahora siempre vacios: su contenido lo definen los tickets de tabla y fixture
    ranking: list = Field(default_factory=list)
    fixture: list = Field(default_factory=list)

class JoinLeagueRequest(LineupConfig):
    team_id: int
    join_token: str | None = None # solo requerido para ligas privadas

class JoinLeagueResponse(BaseModel):
    league_id: int
    team_id: int

class FixtureTeamOut(BaseModel):
    team_id: int
    team_name: str

class FixtureScoreOut(BaseModel):
    home: int
    away: int

class FixtureMatchOut(BaseModel):
    match_id: int
    round_number: int
    status: str
    team_host: FixtureTeamOut
    team_away: FixtureTeamOut
    score: FixtureScoreOut 
