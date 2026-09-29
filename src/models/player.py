"""
Modelo persistente Player.

Representa un jugador de club, asociado a un equipo.
- Contrato de API: POST /api/v1/players.
"""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import UniqueConstraint

from src.database.base import Base

if TYPE_CHECKING:
    from src.models.team import Team


class Player(Base):
    __tablename__ = "players"

    # Restriccion de 2 columnas a la vez, para el n° de camiseta
    # Este numero camiseta no se puede repetir pero en el mismo equipo
    # name="uq_player_team_number" es una etiqueta con nombre
    __table_args__ = (
        UniqueConstraint("team_id", "number", name="uq_player_team_number"),
    )

    # Identificador del jugador 
    player_id : Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # Identificador del Equipo del jugador 
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.team_id", ondelete="CASCADE"), nullable=False
    )

    # Relación con respecto al modelo team.
    team: Mapped["Team"] = relationship(back_populates="player")
    
    # Nombre del jugador
    name : Mapped[str] = mapped_column(String(100), nullable=False)

    # Numero de camiseta del jugador (Numero de camiseta != identificador del jugador)
    number : Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    
    # Power fuerza co la que patea la pelota.
    power : Mapped[int] = mapped_column(Integer, nullable=False)

    # Agility cada cuanto puede volver a patear.
    agility : Mapped[int] = mapped_column(Integer, nullable=False)

    # Control distancia con la que alcanza tocar a la pelota.
    control : Mapped[int] = mapped_column(Integer, nullable=False)

    # Speed rapides con la que correr y aceleracion.
    speed : Mapped[int] = mapped_column(Integer, nullable=False)

    # Strength cuanto se impone en los choques.
    strength : Mapped[int] = mapped_column(Integer, nullable=False)


    def __repr__(self) -> str:
        return (
            f"Player(player_id={self.player_id!r}, name={self.name!r}, "
            f"number={self.number!r}, team_id={self.team_id!r},"
            f"power={self.power!r}, agility={self.agility!r},"
            f"control={self.control!r}, speed={self.speed!r},"
            f"strength={self.strength!r})"
        )
