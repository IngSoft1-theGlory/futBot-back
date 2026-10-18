"""
Consultas de persistencia sobre partidos
Sólo lectura: la escritura vive en src/services/friendly_service.py.
"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload
from src.models import Behavior, LineupEntry, Match, MatchStatus, Player


def get_players_by_team(session: Session, team_id: int) -> list[Player]:
    """Todos los jugadores del equipo."""
    statement = select(Player).where(Player.team_id == team_id)

    # scalars devuelve los objetos sueltos, no envueltos en tuplas
    return list(session.scalars(statement).all())

def get_behaviors_by_ids(session: Session, behavior_ids: list[int]) -> list[Behavior]:
    """Los comportamientos que existan entre esos ids (los que falten no vienen)."""
    statement = select(Behavior).where(Behavior.behavior_id.in_(behavior_ids))
    
    return list(session.scalars(statement).all())

def get_match_by_id(session: Session, match_id: int) -> Match | None:
    """El partido con ese id, o None si no existe."""
    return session.get(Match, match_id)

def get_lineup_entries(session: Session, match_id: int) -> list[LineupEntry]:
    """Las entradas de alineación de AMBOS equipos del partido, en orden de creación."""
    statement = (
        select(LineupEntry)
        .where(LineupEntry.match_id == match_id)
        .order_by(LineupEntry.entry_id)
    )

    return list(session.scalars(statement).all())
  
def get_available_matches(
    session: Session,
    status: MatchStatus | None = MatchStatus.PENDING, # por defecto solo partidos disponibles
    page: int = 1,                                    # por defecto, la primer pagina
    limit: int = 20,                                  # por defecto, 20 partidos por pagina
) -> list[Match]:
    """Devuelve una página de amistosos disponibles"""
    
    # Consulta de partidos disponibles.
    # El estado va fijo el usuario no puede elegir otro.
    match_query = (
        select(Match)
        .options(selectinload(Match.host_team), selectinload(Match.away_team))
        .where(Match.status == status)
        # Agregado en el ticket "Generar fixture de la liga", los partidos de liga viven
        # en esta misma tabla y aparecían en la lista de amistosos. Este filtro le
        # corresponde al ticket del buscador; si lo implementás, ya está hecho aca.
        .where(Match.league_id.is_(None))
    )

    match_query = (
        match_query
        # Ordenar partidos en base a su match_id de forma descendente
        .order_by(Match.match_id.desc())
        # Salta los partidos de las páginas anteriores (página 1 salta 0).
        .offset((page - 1) * limit)
        # Trae como máximo los partidos de una pagina
        .limit(limit)
    )

    # Se ejecuta la consulta y la convierte en lista
    # Si no hay filas, devuelve []
    return list(session.scalars(match_query).all())

def claim_pending_match(session: Session, match_id: int, away_team_id: int) -> bool:
    """Anota al rival y pasa el partido a IN_PROGRESS en un solo UPDATE condicional
    solo lo logra quien lo encuentre todavia PENDING y sin rival: si dos equipos
    compiten, la base deja pasar a uno solo,devuelve False si perdió la carrera, osea
    esto tambien maneja la condicion de carrera
    """
    statement = ( ##aca empieza a construir una consulta SQL
        update(Match) ##indica que queremos hacer un update sobre la tabla de match
        .where( ##las condiciones que deben cumplirse para permitir el update
            Match.match_id == match_id,
            Match.status == MatchStatus.PENDING,
            Match.team_away_id.is_(None), ##osea no tiene que tener un equipo visitante 
        )
        .values(team_away_id=away_team_id, status=MatchStatus.IN_PROGRESS)
    )
    result = session.execute(statement)
    return result.rowcount == 1 ##las filas que modifico, si es 0 es porque no cumplio una condicion y es 1 si salio todo bien y se unio al partido

def get_league_fixture(session: Session, league_id: int) -> list[Match]:
    """ 
    Devuelve todos los partidos de la liga, ordenados por fecha y match_id.
    """
    statement = (   # statement es un objeto que representa la consulta SQL que se va a ejecutar
        select(Match)   # selecciona todos los partidos
        .options(selectinload(Match.host_team), selectinload(Match.away_team)) # carga los equipos anfitrion y visitante de cada partido
        .where(Match.league_id == league_id)    # filtra los partidos de la liga especificada
        .order_by(Match.round_number, Match.match_id)   # ordena los partidos por numero de fecha y match_id
    )
    return list(session.scalars(statement).all())