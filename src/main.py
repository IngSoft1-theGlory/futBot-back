from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from src.config.settings import settings
from src.database.base import get_db
from src.routes.auth import router as auth_router
from src.routes.players import router as players_router
from src.routes.friendly import router as friendly_router
from src.routes.match_result import router as match_result_router
from src.routes.live_token import router as live_token_router
from src.routes.match_live_token import router as match_live_token_router
from src.routes.ws_match import router as ws_match_router
from src.routes.behaviors import router as behaviors_router
from src.routes.ws_global import router as ws_global_router 
from src.routes.match_state import router as match_state_router
from src.routes.substitution import router as substitution_router
from src.routes.leagues import router as join_token_router
from src.routes.leagues import router as leagues_router
from src.routes.rankings import router as rankings_router 

from src.core.exceptions import AppError, app_error_handler

from fastapi import Request 
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# El esquema de la base lo crean las migraciones de Alembic (make migrate), no la app.
app = FastAPI(title=settings.PROJECT_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)  # suma las rutas de /api/v1/auth/*
app.include_router(players_router)  # suma las rutas de /api/v1/players
app.include_router(friendly_router)  # suma las rutas de /api/v1/friendly
app.include_router(match_result_router)  # suma la ruta de /api/v1/matches/{match_id}/result
app.include_router(live_token_router)  # suma las rutas de /api/v1/live-token/*
app.include_router(match_live_token_router) # suma las rutas de /api/v1/matches/*/live-token
app.include_router(ws_match_router) # suma las rutas de /ws/v1/matches/*
app.include_router(behaviors_router)  # suma las rutas de /api/v1/behaviors
app.include_router(ws_global_router)  # suma las rutas de /ws/v1/global
app.include_router(match_state_router)  # suma las rutas de /api/v1/matches/*/state
app.include_router(substitution_router)  # suma la ruta de /api/v1/matches/*/teams/*/substitutions
app.include_router(join_token_router) # /api/v1/leagues/{leagueId}/verify-password
app.include_router(leagues_router) # suma las rutas de /api/v1/leagues
app.include_router(rankings_router)  # suma la ruta de /api/v1/rankings/global

# conecta la función pura de exceptions.py con ESTE app puntual: cada
# vez que algo lance una AppError (o subclase), FastAPI va a llamar
# app_error_handler(request, esa_excepcion) y devolver lo que retorne
app.add_exception_handler(AppError, app_error_handler)

@app.get("/")
def root():
    return {"message": "FutBot Backend API is running"}


@app.get("/api/v1/health", status_code=status.HTTP_200_OK)
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        # este sí es un error inesperado de infraestructura (DB caída),
        # no un AppError de negocio, por eso usa HTTPException directo
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database connection error: {str(e)}",
        )


@app.exception_handler(RequestValidationError)
def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # RequestValidationError lo tira Pydantic/FastAPI antes de que la ruta
    # se ejecute, no es un AppError de negocio, por eso necesita su propio handler.
    return JSONResponse(
        status_code=422,
        content={"error": "VALIDATION_ERROR", "message": "Los datos enviados no son válidos."},
    )
