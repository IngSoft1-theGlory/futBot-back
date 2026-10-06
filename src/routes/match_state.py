""" 
Ruta para obtener el estado de un partido.
"""

from __future__ import annotations
from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from src.core.security import get_current_user
from src.database.base import get_db
from src.schemas.match_state import MatchStateResponse
from src.services.match_state_service import (
    build_match_state_response, load_match_state_context,
)

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