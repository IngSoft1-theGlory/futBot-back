"""
Modelo Team

Contempla:
  * team_id -> Primary Key (autoincremental)
  * name    -> no puede estar vacío (String de hasta 100 caracteres)
  * logo    -> texto largo (Text) que soporta URLs o imágenes en formato Base64
  * user    -> relación 1 a 1 con User (se elimina en cascada desde User)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

# CAMBIO: Importamos Text en lugar de String (o además de String, si se usa en otros campos)
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base

if TYPE_CHECKING:
    from src.models.user import User


class Team(Base):
    __tablename__ = "teams"

    team_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # CAMBIO: Cambiamos String(200) por Text para soportar los strings enormes de base64
    logo: Mapped[str] = mapped_column(Text, nullable=False)

    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="team",
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"Team(team_id={self.team_id!r}, name={self.name!r})"