"""Rutas de ranking global"""

from __future__ import annotations

from math import ceil # ceil viene de ceiling (techo) y sirve para redondear un número hacia arriba

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.core.security import get_current_user
from src.database.base import get_db

from src.schemas.rankings import GlobalRankingResponse, RankingRow
from src.schemas.player import Pagination
from src.services.ranking_service import get_global_ranking


router = APIRouter(prefix="/api/v1/rankings", tags=["ranking"])

@router.get("/global", response_model=GlobalRankingResponse)
def get_global_ranking_endpoint(
    page: str | None = None,
    limit: str | None = None, 
    user_id: int = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> GlobalRankingResponse:

    teams, current_page, limit_per_page, teams_count = get_global_ranking(session, page, limit)

    # calculo el puesto del primer equipo en esta pagina
    position = (current_page - 1) * limit_per_page + 1

    # recorro cada equipo para armar su fila en el ranking
    rows = []
    for team in teams: 
        row = RankingRow(
            position=position, 
            team_id=team.team_id,
            team_name=team.team_name,
            team_logo=team.team_logo,
            points=team.points,
            matches_played=team.matches_played,
            goals_for=team.goals_for,
            goals_against=team.goals_against,
            goal_diff= team.goals_for - team.goals_against,
            wins=team.wins, 
            draws=team.draws,
            losses=team.losses
        )
        rows.append(row) # armo una lista con la fila en el ranking de cada equipo
        position += 1 # el siguiente equipo va un puesto mas abajo

    return GlobalRankingResponse (
        ranking=rows,
        pagination=Pagination(
            current_page=current_page, 
            per_page=limit_per_page,
            total_items=teams_count,
            total_pages=ceil(teams_count / limit_per_page)
        )
    )
    

