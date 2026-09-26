"""
Modelo User — alcance principal de este ticket.

Contempla:
  * user_id       -> Primary Key
  * team_id       -> relación 1 a 1 con Team (FK única, obligatoria)
  * username      -> no puede estar vacío (validado en la capa de servicio,
                     ver app/services/user_service.py)
  * email         -> único en toda la plataforma (constraint a nivel DB)
  * password_hash -> nunca se guarda la contraseña en texto plano
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base

if TYPE_CHECKING:
    from src.models.team import Team


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # 1 a 1 con Team: cada User tiene exactamente un Team, y cada Team
    # pertenece a un único User (unique=True sobre la FK impone la
    # "unicidad" del lado de User; ver Team.user, que también es uselist=False).
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.team_id"),
        unique=True,
        nullable=False,
    )

    username: Mapped[str] = mapped_column(String(50), nullable=False)

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    # Únicamente el hash de la contraseña. `repr=False`-equivalente manual:
    # se excluye a propósito del __repr__ de abajo para que nunca aparezca
    # en logs que hagan `logger.info(user)` o similares.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # cascade="all, delete-orphan" + single_parent=True: al eliminar un User
    # (session.delete(user)), SQLAlchemy elimina también su Team asociado.
    # Esto satisface el criterio de aceptación #4 (eliminar usuario elimina
    # su equipo). single_parent=True es requerido por SQLAlchemy para poder
    # usar delete-orphan en una relación de tipo "uno a uno" / many-to-one.
    team: Mapped["Team"] = relationship(
        "Team",
        back_populates="user",
        uselist=False,
        single_parent=True,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        # A propósito NO incluye `password_hash`: este __repr__ es lo que se
        # imprime si alguien hace `print(user)` o `logger.info("%s", user)`,
        # así que la contraseña (ni su hash) nunca queda expuesta en logs.
        return (
            f"User(user_id={self.user_id!r}, username={self.username!r}, "
            f"email={self.email!r}, team_id={self.team_id!r})"
        )

    def to_public_dict(self) -> dict:
        """
        Representación de este usuario apta para ser devuelta/consultada,
        sin exponer la contraseña (criterio de aceptación #5).

        No implementa serialización HTTP (eso es responsabilidad del
        endpoint de /auth/register u otro que se implemente después); es
        simplemente la forma segura de "leer" un User desde la capa de
        persistencia hacia arriba.
        """
        return {
            "user_id": self.user_id,
            "team_id": self.team_id,
            "username": self.username,
            "email": self.email,
        }
