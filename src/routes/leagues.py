""" 
Rutas relacionadas con ligas.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session  

from src.core.security import get_current_user
from src.database.base import get_db
from src.services.league_service import list_leagues
from src.schemas.league import LeagueListOut


router = APIRouter(prefix="/api/v1/leagues", tags=["leagues"])

@router.get("", response_model=LeagueListOut, dependencies=[Depends(get_current_user)])
def list_leagues_endpoint(
    page: str | None = None,      
    limit: str | None = None,    
    status: str | None = None,  
    session: Session = Depends(get_db),
):
    
    # se llama al service para obtener la lista de ligas, con paginación y filtrado por estado
    leagues = list_leagues(session, status=status, page=page, limit=limit)
    return {"leagues": leagues}