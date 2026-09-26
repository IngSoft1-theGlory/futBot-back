from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session
from src.config.settings import settings


# Configuración del motor (Engine)
# pool_pre_ping verifica que la conexión siga viva antes de ejecutar consultas

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True
 
)   

# Fábrica de sesiones
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Clase base para la definición de los futuros modelos ORM
class Base(DeclarativeBase):
    pass
    
# Dependencia para inyectar la sesión de DB en los endpoints de FastAPI
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()