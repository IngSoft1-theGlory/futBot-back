"""
Fixtures compartidas. SQLite en memoria (StaticPool) para tests rápidos y
aislados, sin depender de la DATABASE_URL real.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.database.base import Base
from src.models import Team, User  # noqa: F401


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db_session = testing_session_local()
    try:
        yield db_session
    finally:
        db_session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()