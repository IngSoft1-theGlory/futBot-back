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

class PointOut(BaseModel):
    x: float
    y: float

class MatchPlayerOut(BaseModel):
    player_id: int
    team_id: int
    name: str
    number: int
    attributes: PlayerAttributesOut
    behavior_id: int | None   # sin default a propósito: hay que pasarlo siempre
    position: PointOut | None
    current_action: str | None

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
    substitutes: list[MatchPlayerOut]   # suplentes, solo del equipo de quien consulta
    phase: str
    pause: PauseOut | None
    ball: PointOut
      
# Peticion para cambiar comportamiento durante un partido
class ChangeBehaviorRequest(BaseModel): 
    behavior_id: int 

# Respuesta para cambiar comportamiento durante un partido
class ChangeBehaviorResponse(BaseModel): 
    player_id: int 
    behavior_id: int
