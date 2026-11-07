"""
Schemas Pydantic del resultado final de un partido (GET /api/v1/matches/{match_id}/result).
Definen la forma del JSON que sale (response).
"""

from __future__ import annotations

from pydantic import BaseModel


# Un equipo dentro del resultado final: quién es y cuántos goles hizo.
class MatchResultTeamOut(BaseModel):
    team_id: int
    team_name: str | None  # Team.team_name es nullable en la base
    goals: int
    penalty_goals: int | None  # goles de penales 


# Lo que devuelve GET /api/v1/matches/{match_id}/result
class MatchResultResponse(BaseModel):
    match_id: int
    status: str  # siempre "FINISHED" (texto, no el Enum)
    home_team: MatchResultTeamOut  # el anfitrión
    away_team: MatchResultTeamOut  # el visitante