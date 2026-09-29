from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from src.config.settings import settings
from src.database.base import Base, engine, get_db
from src.routes.auth import router as auth_router
from src.core.exceptions import AppError, app_error_handler

from fastapi import Request 
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@asynccontextmanager
async def lifespan(app: FastAPI):
    # El esquema de la base ya no se crea acá — lo maneja Alembic
    # Este lifespan es el que se utilizará para Event Bus por ejemplo.
    yield


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)  # suma las rutas de /api/v1/auth/*

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