from __future__ import annotations
from pydantic import BaseModel

# Lo que devuelve el endpoint de estado de partido (GET /matches/{match_id}/state)
class ScoreOut(BaseModel):
    home: int
    away: int

class PlayerAttributesOut(BaseModel):
    power: int
    agility: int
    control: int
    speed: int
    strength: int

class MatchPlayerOut(BaseModel):
    player_id: int
    team_id: int
    name: str
    number: int
    attributes: PlayerAttributesOut
    behavior_id: int | None   # sin default a propósito: hay que pasarlo siempre

class PauseOut(BaseModel):
    type: str
    remaining_seconds: float

# Respuesta del endpoint GET /matches/{match_id}/state.
# Incluye el marcador y los jugadores con sus atributos.
class MatchStateResponse(BaseModel):
    match_id: int
    current_tick: int
    total_ticks: int
    score: ScoreOut
    players: list[MatchPlayerOut]
    phase: str
    pause: PauseOut | None