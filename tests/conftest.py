"""
Fixtures compartidas. SQLite en memoria (StaticPool) para tests rápidos y
aislados, sin depender de la DATABASE_URL real.
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.database.base import Base  
from src.models import Team, User  # noqa: F401


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    # Si está seteada, se usa una DB real (ej: Postgres); si no, SQLite en memoria.
    test_db_url = os.environ.get("TEST_DATABASE_URL")

    if test_db_url:
        engine = create_engine(test_db_url, future=True)
    else:
        # StaticPool: fuerza una única conexión compartida, necesario para que
        # el SQLite en memoria no desaparezca entre queries de un mismo test.
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )

    Base.metadata.create_all(engine)  # crea el schema en la DB elegida

    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db_session = testing_session_local()
    try:
        yield db_session
    finally:
        db_session.close()
        Base.metadata.drop_all(engine)  # limpia todo, incluso si era la DB real
        engine.dispose()