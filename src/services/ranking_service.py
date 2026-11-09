"""
Ranking global de clubes.
lee las estadisticas que acumula global_stats_service
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.core.exceptions import InvalidQueryParamsError
from src.models.team import Team
from src.repositories.team_repository import get_global_ranking_page, get_teams_count
from src.services.player_service import _parse_positive_int

DEFAULT_PAGE = 1
DEFAULT_LIMIT = 50  
MAX_LIMIT = 100

def get_global_ranking(session: Session, page: str | None = None, limit: str | None = None) -> tuple[list[Team], int, int, int]: 
    """ Devuelve (equipos de la pagina, page, limit, total_items) """

    # paso los valores a int con parse_positive_int, que maneja errores si el valor es invalido o None, y ademas setea los valores default
    page_number = _parse_positive_int(page, DEFAULT_PAGE, "page")
    limit_in_page = _parse_positive_int(limit, DEFAULT_LIMIT, "limit")

    if limit_in_page > MAX_LIMIT:
        raise InvalidQueryParamsError(f"limit no puede superar {MAX_LIMIT}.")

    # calculo el offset: para llegar a la pagina N me salteo las anteriores (N-1 paginas de limit_in_page equipos c/una) 
    offset = (page_number - 1) * limit_in_page

    # busco la pagina de equipos
    teams = get_global_ranking_page(session, offset=offset, limit=limit_in_page)

    teams_count = get_teams_count(session) 

    return teams, page_number, limit_in_page, teams_count # devuelvo (equipos, numero de pagina, limite por pagina, cantidad total de equipos)