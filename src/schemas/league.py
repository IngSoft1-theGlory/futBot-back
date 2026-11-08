""" 
Schemas pydantic de ligas
Definen la forma del JSON que entra (request) y el que sale (response)
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal # Literal permite definir un tipo que solo puede tomar ciertos val, ej Literal["IN_PROGRESS"]   

from src.models.league import LeagueStatus
from src.schemas.lineup_config import LineupConfig


class CreateLeagueRequest(LineupConfig):
    league_name: str
    match_duration: int 
    max_teams: int 
    password: str | None = None # si no viene, es None 
    team_id: int
    penalties_enabled: bool = False # si no viene, la liga no tiene penales 
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
    penalties_enabled: bool 

class LeagueOut(BaseModel):
    league_id: int
    league_name: str
    max_teams: int
    current_teams_count: int
    status: LeagueStatus
    is_private: bool
    is_member: bool

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

class FixtureTeamOut(BaseModel):
    team_id: int
    team_name: str

class FixtureScoreOut(BaseModel):
    home: int
    away: int
    phome: int | None = None # goles de penales del anfitrión, solo si hubo penales
    paway: int | None = None # goles de penales del visitante, solo si hubo penales


class FixtureMatchOut(BaseModel):
    match_id: int
    round_number: int
    status: str
    team_host: FixtureTeamOut
    team_away: FixtureTeamOut
    score: FixtureScoreOut 

class StandingRowOut(BaseModel):
    position: int
    team_id: int
    team_name: str
    matches_played: int # partidos jugados
    wins: int           # partido ganado
    draws: int          # partido empatado
    losses: int         # partido perdido
    goals_for: int      # goles a favor
    goals_against: int  # goles en contra
    goal_diff: int      # diferencia de goles
    points: int         # puntos

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
    ranking: list[StandingRowOut] = Field(default_factory=list)
    fixture: list[FixtureMatchOut] = Field(default_factory=list)
    penalties_enabled: bool

class JoinLeagueRequest(LineupConfig):
    team_id: int
    join_token: str | None = None # solo requerido para ligas privadas

class JoinLeagueResponse(BaseModel):
    league_id: int
    team_id: int

class StartLeagueRequest(BaseModel):
    status : Literal["IN_PROGRESS"]

class StartLeagueResponse(BaseModel):
    league_id : int
    league_name : str
    status : LeagueStatus