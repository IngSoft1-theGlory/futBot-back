from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from src.config.settings import settings
from src.core.exceptions import AppError
from src.database.base import Base, engine, get_db
from src.routes.auth import router as auth_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- código de startup (antes del yield) ---
    Base.metadata.create_all(bind=engine)

    yield  # <- acá el server queda corriendo y atendiendo requests

    # --- código de shutdown (después del yield) ---
    # nada por ahora


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


@app.exception_handler(AppError)
def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error_code, "message": exc.message},
    )


@app.get("/")
def root():
    return {"message": "FutBot Backend API is running"}


@app.get("/api/v1/health", status_code=status.HTTP_200_OK)
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database connection error: {str(e)}",
        )