from __future__ import annotations

from pydantic import BaseModel
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