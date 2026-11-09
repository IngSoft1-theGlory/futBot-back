"""Schemas Pydantic para el ranking global"""

from __future__ import annotations

from pydantic import BaseModel

from src.schemas.player import Pagination

class RankingRow(BaseModel):
    position: int
    team_id: int
    team_name: str | None
    team_logo: str | None
    points: int
    matches_played: int
    goals_for: int
    goals_against: int
    goal_diff: int
    wins: int
    draws: int 
    losses: int

class GlobalRankingResponse(BaseModel): 
    ranking: list[RankingRow]
    pagination: Pagination