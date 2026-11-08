"""
Modelo persistente Match.

Una fila por partido. Si league_id es NULL, es un amistoso. Si tiene valor, es
un partido de esa liga. 
El partido guarda el estado, la duracion, los goles y
los equipos anfitrion y visitante.
Las alineaciones de cada equipo estan en lineup_entries.
"""


import enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base

if TYPE_CHECKING:
    from src.models.team import Team


class MatchStatus(enum.Enum):
    PENDING = "PENDING"          # esperando rival (solo esta el anfitrion)
    IN_PROGRESS = "IN_PROGRESS"  # se unio el rival y se esta jugando
    FINISHED = "FINISHED"        


class Match(Base):
    __tablename__ = "matches"

    # Reglas que la base revisa en cada INSERT/UPDATE. Si la fila no las cumple,
    # da IntegrityError. name= es obligatorio por la naming convention del proyecto.
    __table_args__ = (

        CheckConstraint("match_duration > 0", name="duration_positive"),
        # Solo un partido PENDING puede no tener visitante
        CheckConstraint("team_away_id IS NOT NULL OR status = 'PENDING'", name="away_required_unless_pending"),
        # Para evitar que un partido tenga el mismo equipo como anfitrion y visitante
        CheckConstraint("team_host_id != team_away_id", name="host_differs_from_away"),
        CheckConstraint("home_goals >= 0 AND away_goals >= 0", name="goals_non_negative"),
        CheckConstraint("home_penalty_goals >= 0 AND away_penalty_goals >= 0", name="penalty_goals_non_negative"),
    )

    # Identificador unico del partido (lo comparten /friendly y /matches)
    match_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # NULL = amistoso, con valor = partido de esa liga
    league_id: Mapped[Optional[int]] = mapped_column(
    ForeignKey("leagues.league_id", ondelete="CASCADE"), nullable=True, index=True)
    
    # Numero de fecha en la que se juega el partido
    # El numero de fecha es Null en amistoso
    round_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Duracion configurada por el creador del amistoso 
    match_duration: Mapped[int] = mapped_column(Integer, nullable=False)

    # El estado actual. create_constraint=True es para que la base solo acepte esos 3 estados. Al crearse es PENDING
    # index=True: GET /friendly filtra por estado
    status: Mapped[MatchStatus] = mapped_column(
        Enum(MatchStatus, native_enum=False, create_constraint=True, name="status_valid"),
        nullable=False,
        default=MatchStatus.PENDING,
        index=True,
    )

    # Goles: home = anfitrion, away = visitante. default lo pone SQLAlchemy y
    # server_default lo pone la base (por si alguien inserta con SQL directo)
    home_goals: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    away_goals: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # goles de penales. null si el partido no se resuelve por penales
    home_penalty_goals: Mapped[int] = mapped_column(
        Integer, nullable=True, default=None, server_default=None
    )
    away_penalty_goals: Mapped[int] = mapped_column(
        Integer, nullable=True, default=None, server_default=None
    )

    # Equipo anfitrion: obligatorio. CASCADE: si se borra el equipo,
    # la base borra sus partidos. index=True: para buscar los partidos de un equipo
    team_host_id: Mapped[int] = mapped_column(
        ForeignKey("teams.team_id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Equipo visitante: NULL mientras el amistoso espera rival
    team_away_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("teams.team_id", ondelete="CASCADE"), nullable=True, index=True
    )

    # Atajos para llegar al equipo: match.host_team y match.away_team (None si no hay visitante)
    host_team: Mapped["Team"] = relationship(foreign_keys=[team_host_id])
    away_team: Mapped[Optional["Team"]] = relationship(foreign_keys=[team_away_id])


    # Texto legible del partido, para el debugger y los logs.
    def __repr__(self) -> str:
        return (
            f"Match(match_id={self.match_id!r}, match_duration={self.match_duration!r}, "
            f"status={self.status!r}, team_host_id={self.team_host_id!r}, "
            f"team_away_id={self.team_away_id!r}, home_goals={self.home_goals!r}, "
            f"away_goals={self.away_goals!r})"
        )
