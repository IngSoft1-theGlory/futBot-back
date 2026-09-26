"""
Fixtures compartidas para los tests unitarios.

Se usa SQLite en memoria (no el Postgres de docker-compose) para que estos
tests corran rapido y sin depender de tener un servidor de base de datos
levantado. La estructura de las tablas se crea a partir de los mismos
modelos (Base.metadata), asi que si el modelo esta bien definido, funciona
igual contra SQLite que contra Postgres.

Importa los tres modelos (Team, User, Behavior) porque Behavior.user_id
tiene una ForeignKey a "users.user_id": si Base.metadata no conoce la tabla
"users" al momento de crear las tablas, SQLAlchemy no puede resolver esa FK.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.database.base import Base
from src.models.behavior import Behavior  # noqa: F401
from src.models.team import Team  # noqa: F401
from src.models.user import User  # noqa: F401


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session: Session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def usuario_con_equipo(db_session):
    """
    Crea un User + Team persistidos (Behavior.user_id apunta a users.user_id,
    asi que la mayoria de los tests de Behavior necesitan un User real).
    """
    team = Team(name="Sacachispas FC")
    user = User(
        username="messi10",
        email="messi10@example.com",
        password_hash="hash-falso-de-prueba",
        team=team,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user