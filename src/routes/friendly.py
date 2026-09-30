"""
Rutas de amistosos.

Define GET /api/v1/friendly. Recibe page, limit y status, exige sesión
y le pide al service la lista de partidos. No tiene lógica propia:
el 401 lo lanza get_current_user y el 422 lo lanza FastAPI al validar
los query params.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.core.security import get_current_user   
from src.database.base import get_db        
from src.models.match import MatchStatus
from src.schemas.match import FriendlyListOut
from src.services.match_service import list_friendly_matches

router = APIRouter(prefix="/api/v1/friendly", tags=["friendly"])  

# "" y no "/": con "/" la URL sin barra final redirige (307) en vez de responder
@router.get(
    "",
    response_model=FriendlyListOut,
    dependencies=[Depends(get_current_user)],  
)
def list_friendly(
    page: int = Query(1, ge=1),                        # ge=1: page=0 o negativo → 422
    limit: int = Query(20, ge=1, le=100),              # le=100: tope para que nadie pida la tabla entera
    status: MatchStatus = Query(MatchStatus.PENDING),  # valor inválido → 422
    session: Session = Depends(get_db),
):
    matches = list_friendly_matches(session, status=status, page=page, limit=limit)
    return {"matches": matches}