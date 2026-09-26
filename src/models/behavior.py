"""
Modelo persistente Behavior.

Representa un comportamiento predeterminado del sistema
- Contrato de API: GET/POST/DELETE /api/v1/behaviors
"""

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class Behavior(Base):
    __tablename__ = "behaviors"

    # Identificador unico del comportamiento (PK, autoincremental).
    behavior_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # Nombre visible del comportamiento (ej: "Patear pelota").
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Descripcion en lenguaje natural de que hace el comportamiento.
    description: Mapped[str] = mapped_column(String(500), nullable=False)

    # Codigo fuente en Python asociado al comportamiento (puede ser extenso).
    code: Mapped[str] = mapped_column(Text, nullable=False)

    # Dueño del comportamiento. Por ahora es un Integer simple porque el
    # modelo User todavia no existe en el proyecto (es de otro ticket).
    # Cuando exista, reemplazar por:
    #   user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    #   user: Mapped["User"] = relationship(back_populates="behaviors")
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # True si es un comportamiento predeterminado del sistema (no editable/
    # eliminable por el usuario), False si es personalizado.
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    def __repr__(self) -> str:
        return (
            f"Behavior(behavior_id={self.behavior_id!r}, name={self.name!r}, "
            f"is_default={self.is_default!r}, user_id={self.user_id!r})"
        )
