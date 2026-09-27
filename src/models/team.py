"""
Se define la clase Team como modelo de SQLAlchemy — la tabla teams en la base de datos

Modelo Team — STUB MÍNIMO.
Este stub existe únicamente porque User.team_id necesita una tabla real a la
que apuntar como Foreign Key para poder:
  1. Crear la migración de la tabla users.
  2. Probar (tests) la transacción atómica User + Team.
  3. Probar el cascade de borrado User -> Team.
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

    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="team",
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"Team(team_id={self.team_id!r}, name={self.name!r})"