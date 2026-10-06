"""
Consultas de persistencia sobre Player
Solo lectura: la escritura vive en src/services/player_service.py
"""
from __future__ import annotations ## hace que python no evalue las anotaciones de tipo cuando define las funciones, sino que las guarde como strings y las ignore en ejecucion
from sqlalchemy import func, select ## select sirve para construir consultas SQL y func permite utilizar funciones SQL como COUNT() ,SUM() ,AVG() ,MAX() ,MIN()
from sqlalchemy.orm import Session ## session representa la sesión de trabajo con la base de datos
from src.models.player import Player ## importo el modelo de player

##cantidad total de jugadores de un equipo
def get_players_count_by_team_id(session: Session, team_id: int) -> int:
    statement = select(func.count()).select_from(Player).where(Player.team_id == team_id)
    return session.scalar(statement) or 0

##pagina de jugadores del equipo, el orden por numero de camiseta
def get_players_by_team_id(
    session: Session, team_id: int, *, offset: int, limit: int
) -> list[Player]:
    statement = (
        select(Player)
        .where(Player.team_id == team_id)
        .order_by(Player.number)
        .offset(offset)
        .limit(limit)
    )
    return list(session.scalars(statement).all())

"""
1) con select(func.count()) le estamos diciendo a SQLAlchemy que quiero contar registros

2) en select_from(Player) le indicamos de que tabla queremos contar

3) where(Player.team_id == team_id) porque quiero que solo cuente los del equipo de la sesion

4) El * le dice a Python:

    "A partir de aca, los parametros tienen que ser indicados explicitamente por su nombre."

Entonces esto es correcto:

buscar_jugadores(
    session,
    5,
    offset=10,
    limit=20
)
"""
