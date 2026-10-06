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

from math import ceil ##ceil viene de ceiling (techo) y sirve para redondear un número hacia arriba, math es una libreria que ya viene con python

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from src.core.security import get_current_user
from src.database.base import get_db
from src.schemas.player import (
    CreatePlayerRequest,
    Pagination,
    PlayerListItem,
    PlayerListResponse,
    PlayerResponse,
)
from src.services.player_service import create_player, list_players

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



# page/limit se reciben como str a propósito: si FastAPI los tipara como int
# devolvería 422, y el contrato api pide 400 INVALID_QUERY_PARAMS.
@router.get("", response_model=PlayerListResponse) ## Esto le dice a FastAPI Cuando llegue un GET a esta ruta, ejecutá list_players_endpoint
def list_players_endpoint(
    page: str | None = None,
    limit: str | None = None,
    user_id: int = Depends(get_current_user), ## aca se usa Dependency Injection de FastAPI, osea FastAPI se encarga de ejecutar: get_current_user() 
    session: Session = Depends(get_db), ##mismo caso de arriba
) -> PlayerListResponse:
    players, current_page, per_page, total_items = list_players(
        session, user_id=user_id, page=page, limit=limit
    )
    return PlayerListResponse(
        data=[
            PlayerListItem(player_id=p.player_id, name=p.name, number=p.number)
            for p in players
        ],
        pagination=Pagination(
            current_page=current_page,
            per_page=per_page,
            total_items=total_items,
            total_pages=ceil(total_items / per_page),
        ),
    )
"""
lo que hace esta funcion basicamente es recibir una peticion GET, obtener el usuario autenticado, obtener la conexion a la BD, pedirle al player_service los jugadores y finalmente transformar esos datos en la respuesta HTTP
"""