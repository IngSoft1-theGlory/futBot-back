""" 
Schemas pydantic de ligas
Definen la forma del JSON que entra (request) y el que sale (response)
"""

from __future__ import annotations 

from pydantic import BaseModel

from src.models.league import LeagueStatus

class LeagueOut(BaseModel):
    league_id: int
    league_name: str
    max_teams: int
    teams_current: int
    status: LeagueStatus
    is_private: bool

class LeagueListOut(BaseModel):
    leagues: list[LeagueOut]