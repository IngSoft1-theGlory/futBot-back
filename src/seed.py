"""
Carga los comportamientos predeterminados en la base.

Se corre a mano, una vez, DESPUES de `alembic upgrade head`:
    python -m src.seed

Se puede correr todas las veces que haga falta: no duplica nada.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.base import SessionLocal
from src.default_behaviors import DEFAULT_BEHAVIORS
from src.models import Behavior


def seed_default_behaviors(session: Session) -> None:
    """Crea los comportamientos predeterminados, o los actualiza si ya existen."""
    for data in DEFAULT_BEHAVIORS:
        # busco si ya hay un predeterminado con ese nombre
        existing = session.scalars(
            select(Behavior).where(
                Behavior.name == data["name"],
                Behavior.is_default.is_(True),
            )
        ).first()
        
        if existing is not None:
       	    # ya existe: solo actualizo el texto por si cambio desde la ultima vez
            existing.description = data["description"]
            existing.code = data["code"]

        else:
            # no existe: lo creo. No se le pasa user_id porque es del sistema, no de un usuario
            session.add(
                Behavior(
                    name=data["name"],
                    description=data["description"],
                    code=data["code"],
                    is_default=True,
                )
            )

    # un solo commit al final: se guarda todo junto
    session.commit()


# esto solo corre con `python -m src.seed`, y no cuando otro archivo hace `import src.seed`
if __name__ == "__main__":
    with SessionLocal() as session:
        seed_default_behaviors(session)
    print("Comportamientos predeterminados cargados.")
