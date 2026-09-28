"""
Se define la clase Team como modelo de SQLAlchemy — la tabla teams en la base de datos
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database.base import Base

if TYPE_CHECKING:
    from src.models.user import User


class Team(Base):
    __tablename__ = "teams"

    team_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # nullable=True acá porque el que no puede estar vacío lo controlamos en
    # el service (validate_team_name), no en la columna. si lo pusiéramos
    # obligatorio acá, una cadena de espacios ("   ") igual pasaría
    team_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    team_logo: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # sin cascade acá a propósito: la cascada vive del lado de User (que es
    # quien tiene la FK). ponerla también acá sería duplicar la regla en
    # los dos lados sin necesidad
    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="team",
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"Team(team_id={self.team_id!r}, team_name={self.team_name!r})"

    def to_public_dict(self) -> dict:
        """ Diccionario para mostrar datos en publicos """
        return {
            "team_id": self.team_id,
            "team_name": self.team_name,
            "team_logo": self.team_logo,
        }