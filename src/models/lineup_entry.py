"""
Modelo persistente LineupEntry.

Una fila por jugador de la configuracion tactica de un equipo en un partido
"""

from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.database.base import Base


class LineupEntry(Base):
    __tablename__ = "lineup_entries"
    
    __table_args__ = (
        # Un jugador no puede aparecer dos veces en el mismo partido.
        UniqueConstraint("match_id", "player_id", name="uq_lineup_entries_match_player"),

        # Dos jugadores del mismo equipo no pueden tener el mismo rol en un partido
        UniqueConstraint("match_id", "team_id", "role", name="uq_lineup_entries_match_team_role"),

        # Los titulares deben tener rol asignado, los suplentes no 
        CheckConstraint(
            "(is_starter AND role IS NOT NULL) OR (NOT is_starter AND role IS NULL)",
            name="only_starter_has_role",
        ),
        # Solo los seis roles permitidos pueden asignarse a un jugador
        CheckConstraint(
            "role IN ('DEF_LEFT', 'DEF_RIGHT', 'FORWARD', 'DEFENDER', 'FORWARD_LEFT', 'FORWARD_RIGHT')",
            name="role_valid",
        ),
    )

    entry_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Partido al que pertenece. Si se borra el partido, se borran sus entries.
    # NOT NULL por ahora. al implementar ligas debera ser nullable (y habra que poner league_id en la tabla)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.match_id", ondelete="CASCADE"), nullable=False
    )

    # Equipo al que pertenece esta configuracion. Si se borra el equipo, se borran sus entries
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.team_id", ondelete="CASCADE"), nullable=False
    )

    # Jugador. index = True es para buscar en que partidos juega un jugador
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.player_id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Comportamiento asignado. Sin ondelete porque la base no deja borrar un comportamiento en uso
    behavior_id: Mapped[int] = mapped_column(
        ForeignKey("behaviors.behavior_id"), nullable=False
    )

    # Para asignar si son delanteros, defensa izquierda, etc. Es nullable porque los suplentes no tienen rol asignado al iniciar el partido
    role: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # true indica titular, false indica suplente  
    is_starter: Mapped[bool] = mapped_column(Boolean, nullable=False)
