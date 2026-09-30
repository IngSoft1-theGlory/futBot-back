"""
Rutas de jugadores.

Igual que routes/auth.py: solo traduce HTTP <-> dominio. La validación
vive en player_service (osea las reglas para crear un jugador están en player_service, no aca) 
y los errores los traduce el handler (manejar) global de
AppError (osea si ocurre un error, existe otro componente encargado de convertir ese error en una respuesta HTTP). 
get_current_user corre antes de leer el body, así que un token
inválido responde 401 aunque el body también sea inválido.
"""

from __future__ import annotations ##Esto modifica cómo Python interpreta las anotaciones de tipos

from fastapi import APIRouter, Depends, status 
from sqlalchemy.orm import Session

from src.core.security import get_current_user
from src.database.base import get_db
from src.schemas.player import CreatePlayerRequest, PlayerResponse
from src.services.player_service import create_player

router = APIRouter(prefix="/api/v1/players", tags=["players"])

@router.post("", response_model=PlayerResponse, status_code=status.HTTP_201_CREATED)
def create_player_endpoint(
    payload: CreatePlayerRequest,
    user_id: int = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> PlayerResponse:
    player = create_player(
        session,
        user_id=user_id,
        name=payload.name,
        number=payload.number,
        power=payload.power,
        agility=payload.agility,
        control=payload.control,
        speed=payload.speed,
        strength=payload.strength,
    )
    return PlayerResponse(
        player_id=player.player_id,
        name=player.name,
        number=player.number,
        power=player.power,
        agility=player.agility,
        control=player.control,
        speed=player.speed,
        strength=player.strength,
    )

