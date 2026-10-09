from __future__ import annotations
from fastapi import APIRouter, Depends
from src.schemas.league import VerifyPasswordRequest, VerifyPasswordResponse
from src.core.security import get_current_user, create_join_token 
from src.services.league_service import check_league_password
from src.database.base import get_db
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1/leagues", tags=["leagues"]) 

@router.post("/{league_id}/verify-password", response_model=VerifyPasswordResponse)
def verify_league_password(
    league_id: int,
    payload: VerifyPasswordRequest,
    user_id: int = Depends(get_current_user),
    session: Session = Depends(get_db),
):
    check_league_password(session, league_id, payload.password)
    return VerifyPasswordResponse(
        join_token=create_join_token(user_id, league_id),
        expires_in_seconds=300,
    )