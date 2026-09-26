"""
Fixtures compartidas. SQLite en memoria (StaticPool) para tests rápidos y
aislados, sin depender de la DATABASE_URL real.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from collections.abc import Generator
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.database.database import Base
from src.models import Team, User  # noqa: F401



@pytest.fixture()
@pytest.fixture()
def session() -> Generator[Session, None, None]:
    ...
    yield db_session
    ...
    
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