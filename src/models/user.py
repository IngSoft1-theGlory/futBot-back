"""
Se define la clase User como modelo de SQLAlchemy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database.base import Base


if TYPE_CHECKING:
    from src.models.team import Team
    from src.models.team import Behavior


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # obligatorio (nullable=False): todo user se crea siempre junto con su
    # team, nunca existe uno sin el otro. unique=True: un team no se puede
    # compartir entre dos users
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.team_id"),
        unique=True,
        nullable=False,
    )

    username: Mapped[str] = mapped_column(String(50), nullable=False)

    # unique + index porque lo usamos para loguearse y para chequear
    # duplicados en el registro
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    # nunca se guarda la password en texto plano, sólo el hash
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # cascada : en cascade="all, delete-orphan", si se borra el usurio 
    # se elimina tambien el team asociado
    team: Mapped["Team"] = relationship(
        "Team",
        back_populates="user",
        uselist=False,
        single_parent=True,
        cascade="all, delete-orphan",
    )

    # Lado inverso de Behavior.user (necesario porque Behavior declara
    # back_populates="behaviors"). Un usuario puede tener muchos
    # comportamientos personalizados; si se borra el User, sus
    # comportamientos se borran con él (cascade), no quedan huérfanos.
    behaviors: Mapped[list["Behavior"]] = relationship(
        "Behavior",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # Metodo especial para mostar el objeto con campos, como en el debugger,
    # no se incluye el password_hash. 
    def __repr__(self) -> str:
        return (
            f"User(user_id={self.user_id!r}, username={self.username!r}, "
            f"email={self.email!r}, team_id={self.team_id!r})"
        )

    # lo que se manda para afuera en las respuestas: mismo motivo que el
    # repr de arriba, password_hash no tiene nada que hacer viajando por ahí
    def to_public_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "team_id": self.team_id,
            "username": self.username,
            "email": self.email,
        }