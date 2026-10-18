""" 
Ruta para obtener el estado de un partido.
"""

from __future__ import annotations
from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from src.core.security import get_current_user
from src.database.base import get_db
from src.schemas.match_state import MatchStateResponse, ChangeBehaviorRequest, ChangeBehaviorResponse
from src.services.match_state_service import (
    build_match_state_response, load_match_state_context,
)
from src.services.match_player_service import validate_behavior_change, apply_behavior_change

router = APIRouter(prefix="/api/v1/matches", tags=["matches"])


@router.get("/{match_id}/state", response_model=MatchStateResponse)
async def get_match_state_endpoint(
    match_id: int,
    user_id: int = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> MatchStateResponse:
    context = await run_in_threadpool(load_match_state_context, session, user_id, match_id)
    # sin ningun await de aca en adelante
    return build_match_state_response(context)


@router.put("/{match_id}/players/{player_id}/behavior", response_model=ChangeBehaviorResponse)
def change_behavior_on_match_endpoint(
    payload: ChangeBehaviorRequest,
    player_id: int,
    match_id: int,
    user_id: int = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> ChangeBehaviorResponse:

    team_id, code = team_id, code = validate_behavior_change(session, user_id, match_id, payload.behavior_id)

    apply_behavior_change(match_id, team_id, code, player_id, payload.behavior_id)

    return ChangeBehaviorResponse(player_id=player_id, behavior_id=payload.behavior_id)