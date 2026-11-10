""" 
Consulta de persistencia de ligas
Solo lectura: la escritura vive en src/services/league_service.py 
"""

from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from src.models import League, LeagueStatus, LineupEntry, Team


def get_leagues(
        session: Session, 
        statuses: list[LeagueStatus] | None = None,  # por defecto None, devuelve todas las ligas.
        page: int = 1,                               # por defecto, la primer pagina
        limit: int = 20                              # por defecto, 20 ligas por pagina
):
    """ 
    Obtiene un listado de todas las ligas, con paginación y filtrado por estado.
    por defecto devuelve todas las ligas, pero si se pasa una lista de estados,
    devuelve solo las ligas que estén en alguno de esos estados.
    """
    
    # Subconsulta: por cada liga, cuántos equipos distintos
    # tienen filas en lineup_entries
    subquery = (
        select(func.count(LineupEntry.team_id.distinct()))  # cuenta de equipos distintos sin contar duplicados
        .where(LineupEntry.league_id == League.league_id)   # solo las filas de esa liga
        .scalar_subquery()                                  # devuelve un solo valor, no una lista de filas
    )

    # Se selecciona la liga y el conteo de equipos anotados en la subconsulta
    query = select(League, subquery.label("team_count"))

    # si statuses es None, devuelve todas las ligas; si no, se queda con las ligas
    # cuyo estado esté en la lista (en SQL: WHERE status IN ('PENDING', 'IN_PROGRESS'))
    if statuses is not None:
        query = query.where(League.status.in_(statuses))

    # Se ordena por league_id descendente, se salta los de las páginas anteriores 
    # y se limita a la cantidad de ligas por página
    query = (
        query
        .order_by(League.league_id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )

    # Devuelve una lista de tuplas (League, team_count)
    return session.execute(query).all()


def get_league_by_id(session: Session, league_id: int, for_update: bool = False) -> League | None:
    """ Devuelve la liga con ese id, o None si no existe 
    y bloquea la fila para update si for_update es True. """
    return session.get(League, league_id, with_for_update=for_update)


def get_league_teams(session: Session, league_id: int) -> list[Team]:
    """
    Devuelve los equipos inscriptos en la liga (los que tienen filas en
    lineup_entries con ese league_id), sin duplicados y en orden de inscripcion.
    Cada equipo tiene 6 filas, por eso se agrupa por equipo y se ordena por su
    primera fila: el anfitrion queda primero porque su alineacion se guarda al crear la liga.
    """
    query = (
        select(Team)
        .join(LineupEntry, LineupEntry.team_id == Team.team_id)
        .where(LineupEntry.league_id == league_id)
        .group_by(Team.team_id)
        .order_by(func.min(LineupEntry.entry_id))
    )
    return list(session.scalars(query).all())

def is_team_in_league(session: Session, league_id: int, team_id: int) -> bool:
    """ Verifica si un equipo esta inscripto en una liga """
    statement = (
        select(LineupEntry.entry_id)               # selecciona solo el id de la entrada, no toda la fila
        .where(LineupEntry.league_id == league_id, LineupEntry.team_id == team_id) # filtra por liga y equipo
        .limit(1)                                  # limita a una sola fila
    )  
    # Devuelve true si existe al menos una fila, false si no
    return session.scalar(statement) is not None

def get_member_league_ids(session: Session, team_id: int, league_ids: list[int]) -> set[int]:
    """ Devuelve, de las ligas indicadas, en cuáles está inscripto el equipo """
    statement = (
        select(LineupEntry.league_id)   # selecciona solo el id de la liga
        .where(LineupEntry.team_id == team_id, LineupEntry.league_id.in_(league_ids)) # filtra por equipo y ligas 
        .distinct()   # el equipo tiene 6 filas por liga, así cada liga aparece una sola vez
    )
    return set(session.scalars(statement).all())