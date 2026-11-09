"""
Se define la clase Team como modelo de SQLAlchemy — la tabla teams en la base de datos
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base

if TYPE_CHECKING:
    from src.models.user import User
    from src.models.player import Player


class Team(Base):
    __tablename__ = "teams"

    team_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # nullable=True acá porque el que no puede estar vacío lo controlamos en
    # el service (validate_team_name), no en la columna. si lo pusiéramos
    # obligatorio acá, una cadena de espacios ("   ") igual pasaría
    team_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    team_logo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    """
    Estadisticas globales del club, las que usa el ranking global
    
    Solo las cambia global_stats_service, cuando termina un partido de una liga publica
    
    Mapped[int] ya dice que es un numero entero y que no puede quedar vacio (no es Optional)
    
    default lo pone SQLAlchemy y server_default lo pone la base (los equipos que ya existian arrancan en 0)
    """
    matches_played: Mapped[int] = mapped_column(default=0, server_default="0")  # partidos jugados
    wins: Mapped[int] = mapped_column(default=0, server_default="0")            # ganados
    draws: Mapped[int] = mapped_column(default=0, server_default="0")           # empatados
    losses: Mapped[int] = mapped_column(default=0, server_default="0")          # perdidos
    goals_for: Mapped[int] = mapped_column(default=0, server_default="0")       # goles a favor
    goals_against: Mapped[int] = mapped_column(default=0, server_default="0")   # goles en contra
    points: Mapped[int] = mapped_column(default=0, server_default="0")          # puntos

    # sin cascade acá a propósito: la cascada vive del lado de User (que es
    # quien tiene la FK). ponerla también acá sería duplicar la regla en
    # los dos lados sin necesidad
    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="team",
        uselist=False,
    )

    # Lado inverso de Player.team (necesario porque Player declara
    # back_populates="players"). Un Equipo puede tener muchos jugadores,
    players: Mapped[list["Player"]] = relationship(
        back_populates="team",
        cascade="all, delete-orphan",
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
