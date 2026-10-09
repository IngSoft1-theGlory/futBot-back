""" 
Consulta de persistencia de ligas
Solo lectura: la escritura vive en src/services/league_service.py 
"""

from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from src.models import League, LeagueStatus, LineupEntry


def get_leagues(
        session: Session, 
        status: LeagueStatus | None,    # por defecto None, devuelve todas las ligas.
        page: int = 1,                  # por defecto, la primer pagina
        limit: int = 20                 # por defecto, 20 ligas por pagina
):
    """ 
    Obtiene un listado de todas las ligas, con paginación y filtrado por estado.
    por defecto devuelve todas las ligas, pero si se pasa un estado, filtra por ese estado.
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

    # si el estado es None, devuelve todas las ligas, si no, filtra por el estado
    if status is not None:
        query = query.where(League.status == status)

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

def get_league_by_id(
        session: Session, 
        league_id: int
) -> League | None:
    """ Obtiene una liga por su ID, o None si no existe"""
    return session.get(League, league_id)


def is_team_in_league(session: Session, league_id: int, team_id: int) -> bool:
    """ Verifica si un equipo esta inscripto en una liga """
    statement = (
        select(LineupEntry.entry_id)               # selecciona solo el id de la entrada, no toda la fila
        .where(LineupEntry.league_id == league_id, LineupEntry.team_id == team_id) # filtra por liga y equipo
        .limit(1)                                  # limita a una sola fila
    )  
    # Devuelve true si existe al menos una fila, false si no
    return session.scalar(statement) is not None