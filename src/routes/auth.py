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

from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session

from src.database.base import get_db
from src.schemas.auth import RegisterRequest, RegisterResponse, LoginRequest, LoginResponse, UserOut

from src.repositories.user_repository import get_user_by_email
from src.core.security import verify_password, create_access_token
from src.services.user_service import create_user_with_team
from src.core.exceptions import InvalidCredentialsError

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    session: Session = Depends(get_db),
) -> RegisterResponse:
    user = create_user_with_team(
        session,
        username=payload.username,
        email=payload.email,
        password=payload.password,
        team_data={"team_name": payload.team_name, "team_logo": payload.team_logo},
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

@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:

    user = get_user_by_email(db, payload.email)

    # 2. si no existe, o si la password no matchea (verify_password),
    #    tirar el mismo HTTPException(401, detail={"error": "INVALID_CREDENTIALS", "message": "Email o contraseña incorrecto"})
    #    — mismo bloque para los dos casos, no dupliques el raise

    if user == None or not verify_password(payload.password, user.password_hash):
        raise InvalidCredentialsError("Email o contraseña incorrecto")
    # 3. generar el token con create_access_token

    jwt_firm = create_access_token(user.user_id)
    # 4. devolver LoginResponse(token=..., token_type="Bearer", user=UserOut(...))
    response = LoginResponse(token = jwt_firm, token_type="Bearer", user=UserOut(user_id=user.user_id, team_id=user.team_id, username=user.username, email=user.email))


    return response