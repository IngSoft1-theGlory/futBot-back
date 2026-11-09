"""
Ruta para hacer una sustitución de jugadores (en una pausa) o dejarla planificada (fuera de ella).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from src.core.security import get_current_user
from src.database.base import get_db
from src.schemas.substitution import SubstitutionRequest, SubstitutionResponse
from src.services.substitution_service import SubstitutionResult, apply_substitution, validate_substitution

router = APIRouter(prefix="/api/v1/matches", tags=["matches"])


@router.post(
    "/{match_id}/teams/{team_id}/substitutions",
    response_model=SubstitutionResponse,
    status_code=201,  # cambio aplicado en la pausa; si queda planificado se cambia a 202 más abajo
    responses={202: {"model": SubstitutionResponse, "description": "El cambio quedó planificado para la próxima pausa"}},
)
async def substitution_endpoint(
    payload: SubstitutionRequest,
    match_id: int,
    team_id: int,
    response: Response,
    user_id: int = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> SubstitutionResponse:

    # consulta la base, que es lento. es en un hilo aparte y con await para
    # no frenar al event loop mientras espera
    await run_in_threadpool(validate_substitution, session, user_id, team_id)

    # cambio o plan en memoria, que es rapido. sin await de aca en adelante, asi corre de
    # corrido y el motor no puede correr un tick a la mitad
    result = apply_substitution(match_id, team_id, payload.player_in_id, payload.player_out_id)

    # 201 si el cambio se aplicó en la pausa; 202 si quedó planificado para la próxima
    if result == SubstitutionResult.PLANNED:
        response.status_code = 202

    return SubstitutionResponse(
        match_id=match_id,
        team_id=team_id,
        player_in_id=payload.player_in_id,
        player_out_id=payload.player_out_id,
    )
