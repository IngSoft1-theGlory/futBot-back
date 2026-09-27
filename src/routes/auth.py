"""
Rutas de autenticación.

Esta capa solo traduce HTTP <-> dominio: arma el team_data a partir del
body, llama al service, y arma la response. No valida nada (es
responsabilidad de user_service.create_user_with_team) ni atrapa
excepciones (las traduce a JSON el exception handler global de AppError,
registrado en src/main.py) — así cualquier endpoint nuevo del contrato
puede seguir este mismo patrón sin repetir manejo de errores.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from src.database.base import get_session
from src.schemas.auth import RegisterRequest, RegisterResponse
from src.services.user_service import create_user_with_team

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    session: Session = Depends(get_session),
) -> RegisterResponse:
    user = create_user_with_team(
        session,
        username=payload.username,
        email=payload.email,
        password=payload.password,
        team_data={"name": payload.team_name, "logo": payload.team_logo},
    )

    # team_name/team_logo se devuelven desde el payload (no desde user.team)
    # para evitar un round-trip extra a la DB: no sufren ninguna
    # transformación entre el request y lo persistido.
    return RegisterResponse(
        user_id=user.user_id,
        team_id=user.team_id,
        username=user.username,
        email=user.email,
        team_name=payload.team_name,
        team_logo=payload.team_logo,
    )