""" 
Modelo de ligas
"""

from src.database.base import Base
from sqlalchemy import CheckConstraint, Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
import enum
from typing import Optional

class LeagueStatus(enum.Enum):
    PENDING = "PENDING"          # esperando rivales
    IN_PROGRESS = "IN_PROGRESS"  # los partidos de la liga se estan jugando
    FINISHED = "FINISHED"        

class League(Base):
    __tablename__ = "leagues"

    __table_args__ = (
    CheckConstraint("match_duration > 0", name="duration_positive"),
    CheckConstraint("max_teams BETWEEN 4 AND 12 AND max_teams IN (4, 6, 8, 10, 12)", name="capacity_valid"),
    )

    CheckConstraint(
        "(is_starter AND role IS NOT NULL) OR (NOT is_starter AND role IS NULL)", name="only_starter_has_role",
        ),

    league_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    league_name: Mapped[str] = mapped_column(Text, nullable = False)

    # cupo maximo par, entre 4 y 12 
    max_teams: Mapped[int] = mapped_column(Integer, nullable = False)

    # El estado actual. create_constraint=True es para que la base solo acepte esos 3 estados. Al crearse es PENDING
    # index=True: GET /api/v1/leagues filtra por estado
    status: Mapped[LeagueStatus] = mapped_column(
        Enum(LeagueStatus, native_enum=False, create_constraint=True, name="status_valid"),
        nullable=False,
        default=LeagueStatus.PENDING,
        index=True,
    )

    # en la request va la password en la response va is_private dependiendo de si es null o no 
    password_hash: Mapped[Optional[str]] = mapped_column(Text, nullable = True)

    # aca solo valido que sea positiva, luego el service chequea que sea 2 o 5
    match_duration: Mapped[int] = mapped_column(Integer, nullable=False)

    # Equipo anfitrion: obligatorio. 
    # CASCADE: si se borra el equipo anfitrión, se borra su liga
    # index=True: para buscar las ligas de un equipo
    host_team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.team_id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # para que imprima los datos claramente si un test falla, en vez de <League object at 0x...> 
    def __repr__(self) -> str:
        return (
            f"League(league_id={self.league_id!r}, league_name={self.league_name!r}, "
            f"status={self.status!r}, max_teams={self.max_teams!r})"
        )