"""
Modelo persistente Behavior.

Representa un comportamiento predeterminado del sistema
- Contrato de API: GET/POST/DELETE /api/v1/behaviors
"""

from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base

if TYPE_CHECKING:
    from src.models.user import User


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

    # Dueño del comportamiento (nullable porque los comportamientos
    # is_default=True son del sistema y no pertenecen a ningún usuario).
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=True
    )

    # Relación con respecto al modelo users.
    user: Mapped[Optional["User"]] = relationship(back_populates="behaviors")

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
