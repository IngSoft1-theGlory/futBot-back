"""
Modelo Team — STUB MÍNIMO, no es el alcance de este ticket.

El modelo completo de Team (team_name, team_logo, validaciones, servicios,
endpoints propios) pertenece al ticket "[BACK] Implementar modelos y
persistencia de equipo". Ese ticket puede y debe reemplazar/extender esta
clase (agregar columnas, constraints, validaciones, etc.) sin romper la
relación 1 a 1 con User que se define acá.

Este stub existe únicamente porque User.team_id necesita una tabla real a la
que apuntar como Foreign Key para poder:
  1. Crear la migración de la tabla `users`.
  2. Probar (tests) la transacción atómica User + Team.
  3. Probar el cascade de borrado User -> Team.

Se agrega un único campo genérico (`name`) sólo para que la operación
`create_user_with_team` tenga algo concreto que persistir como "datos del
equipo"; no implementa ningún tipo de validación (ni de nombre ni de logo),
que es responsabilidad exclusiva del ticket de Team.
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

    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Tener en cuenta que por estandar el logo suele ser una URL y el largo puede variar
    # nulleable=False permite que si alguien llama a Team desde una migración u otro lado
    # que no sea create_user_with_team, la constraint de la tabla impida que hayan datos inconsistentes
    # incluso si se saltean la validación de negocio con la base de datos, son fines robustos.
    logo: Mapped[str] = mapped_column(String(200), nullable=False)

    # NOTA para el ticket de estadísticas/Team: cuando exista un modelo de
    # estadísticas de equipo, debe colgar de Team (no de User) con su propio
    # `relationship(..., cascade="all, delete-orphan")`, de forma que al
    # eliminarse el Team (ya ocurre en cascada al eliminar el User, ver
    # app/models/user.py) se eliminen también sus estadísticas.
    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="team",
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"Team(team_id={self.team_id!r}, name={self.name!r})"