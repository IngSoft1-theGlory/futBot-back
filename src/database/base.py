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

# Convención de nombres para constraints/índices. Fija nombres predecibles
# (ej: "uq_users_email") en vez de los que autogeneraría cada motor de DB,
# lo cual hace que Alembic pueda autogenerar migraciones de forma consistente
# y que el código de manejo de errores pueda reconocer qué constraint falló.
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


# URL de conexión configurable por variable de entorno. Por defecto usa un
# archivo SQLite local para poder levantar el proyecto sin infraestructura
# adicional; en producción se espera que DATABASE_URL apunte a Postgres.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./futbot.db")

# `connect_args` sólo es necesario para SQLite (permite usarlo en tests con
# distintos threads); en otros motores se ignora porque no se pasa.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, echo=False, future=True, connect_args=_connect_args)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """
    Generador de sesiones para inyección de dependencias (ej. en FastAPI).
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
