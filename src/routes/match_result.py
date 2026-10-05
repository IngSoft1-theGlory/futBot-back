from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.core.security import get_current_user
from src.database.base import get_db
from src.schemas.match_result import MatchResultResponse
from src.services.match_result_service import get_match_result

# Todas las rutas de este archivo empiezan con /api/v1/matches
router = APIRouter(prefix="/api/v1/matches", tags=["match-result"])


# GET /api/v1/matches/{match_id}/result
@router.get(
    "/{match_id}/result",
    response_model=MatchResultResponse,
    # solo pide que el usuario esté logueado (o 401); cualquiera puede ver el resultado de cualquier partido
    dependencies=[Depends(get_current_user)],
)
def get_match_result_endpoint(
    match_id: int,
    session: Session = Depends(get_db),
) -> MatchResultResponse:
    """Devuelve el resultado final de un partido que ya terminó."""

    # busca el partido; si no existe lanza 404 MATCH_NOT_FOUND y si no terminó, 400 MATCH_NOT_FINISHED
    match = get_match_result(session, match_id)

    # un partido FINISHED siempre tiene visitante (la base no lo permite sin él),
    # así que away_team nunca es None acá
    return MatchResultResponse(
        match_id=match.match_id,
        status=match.status.value,  # get_match_result solo deja pasar FINISHED
        home_team={
            "team_id": match.host_team.team_id,
            "team_name": match.host_team.team_name,
            "goals": match.home_goals,
        },
        away_team={
            "team_id": match.away_team.team_id,
            "team_name": match.away_team.team_name,
            "goals": match.away_goals,
        },
    )
