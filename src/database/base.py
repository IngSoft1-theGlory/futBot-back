"""
Configuración central de SQLAlchemy (estilo 2.0).

No existía código previo en el repositorio, así que este módulo define desde
cero las piezas mínimas y estándar que cualquier modelo del proyecto va a
necesitar: la `Base` declarativa, el engine y la fábrica de sesiones.

Cualquier otro ticket de backend (Team, Player, Behavior, League, Match...)
debe reutilizar este mismo `Base` y esta misma `SessionLocal`, no crear los
suyos propios, para que todos los modelos vivan en el mismo `MetaData` y las
migraciones de Alembic los detecten a todos.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata_obj = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Base declarativa compartida por todos los modelos del proyecto."""

    metadata = metadata_obj


DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./futbot.db")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, echo=False, future=True, connect_args=_connect_args)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """
    Generador de sesiones para inyección de dependencias (ej. en FastAPI).
    No se usa desde este ticket, pero el desarrollador de `/auth/register`
    lo va a necesitar como `Depends(get_session)`.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()