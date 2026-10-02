from __future__ import annotations

from pydantic import BaseModel


class StartingPlayer(BaseModel):
    player_id: int
    role: str
    behavior_id: int


class SubstitutePlayer(BaseModel):
    player_id: int
    behavior_id: int


class LineupConfig(BaseModel):
    formation_type: str
    starting_players: list[StartingPlayer]
    substitute_players: list[SubstitutePlayer]

    