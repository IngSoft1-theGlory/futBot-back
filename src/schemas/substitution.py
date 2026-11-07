"""
Schemas del endpoint de sustitución de jugadores.
"""

from pydantic import BaseModel


# Petición para hacer un cambio (en una pausa) o dejarlo planificado (fuera de ella)
class SubstitutionRequest(BaseModel):
    player_in_id: int    # el suplente que entra a la cancha
    player_out_id: int   # el titular que sale al banco


# Respuesta del cambio. Es la misma para el 201 (aplicado) y el 202 (planificado).
# No hay substitution_id: el cambio no se guarda en la base.
class SubstitutionResponse(BaseModel):
    match_id: int
    team_id: int
    player_in_id: int
    player_out_id: int
