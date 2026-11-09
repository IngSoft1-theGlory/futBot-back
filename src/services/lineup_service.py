"""
Configuración de un partido: guardado y validación de lo que elige un equipo
antes de jugar (duración, equipo, jugadores, formación y comportamientos).

Lo usan todos los endpoints que arman una configuración de partido
(amistoso, liga), así las reglas viven en un solo lugar.

- validate_*  : chequeos sueltos (equipo del usuario, duración, mínimo de jugadores).
- validate_lineup : formación, jugadores y comportamientos de la alineación.
- save_lineup : guarda la alineación en la DB 
"""

from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from src.models.behavior import BehaviorType
from src.models.lineup_entry import LineupEntry
from src.schemas.lineup_config import LineupConfig
from src.core.exceptions import ForbiddenError, InvalidConfigurationError, InvalidSettingsError, PreconditionFailedError
from src.repositories.match_repository import get_behaviors_by_ids, get_players_by_team, get_lineup_entries
from src.repositories.user_repository import get_user_by_id
from src.models.match import Match 

STARTERS_COUNT = 3      # titulares por equipo
SUBSTITUTES_COUNT = 3   # suplentes por equipo
INVALID_LINEUP_MESSAGE = "La formación o la alineación seleccionados no es válida."


# para cada formación, los roles que deben ocupar los titulares
FORMATION_ROLES = {
    "2-1": {"DEF_LEFT", "DEF_RIGHT", "FORWARD"},
    "1-2": {"DEFENDER", "FORWARD_LEFT", "FORWARD_RIGHT"},
}

# Guardar alineación en la DB (league_id: int | None porque puede ser null, como match_id)
# Pero el = None es para q python lo tome como None por defecto si no se especifica al llamar a save_lineup (asi no rompo nada de lo que hicimos antes de implementar ligas))
def save_lineup(session: Session, match_id:int | None, team_id: int, config: LineupConfig, league_id: int | None = None) -> None:
    """Se usa cada vez que un equipo confirma su alineación para un partido o liga:
    el anfitrión al crearlos, los rivales al unirse.
    Antes hay que llamar a validate_lineup, y el partido/liga ya tiene que tener su id (flush).
    No hace commit: lo hace quien la llama, para que todo se guarde (o se deshaga) junto."""       

    # 3 titulares con rol
    for starter in config.starting_players:
        session.add(LineupEntry(
            match_id = match_id,
            league_id = league_id,
            team_id = team_id,
            player_id = starter.player_id,
            behavior_id = starter.behavior_id,
            role = starter.role,
            is_starter = True,
        ))

    # 3 suplentes sin rol
    for substitute in config.substitute_players:
        session.add(LineupEntry(
            match_id = match_id,
            league_id = league_id,
            team_id = team_id,
            player_id = substitute.player_id,
            behavior_id = substitute.behavior_id,
            role = None,
            is_starter = False,
        ))

def replace_league_lineup(session: Session, league_id: int, team_id: int, config: LineupConfig) -> None:
    """Reemplaza la alineación del equipo en la liga. No hace commit: lo hace quien la llama"""

    # el delete se ejecuta en el momento, así las filas nuevas no chocan con las viejas (mismo jugador o rol)
    session.execute(delete(LineupEntry).where(LineupEntry.league_id == league_id, LineupEntry.team_id == team_id))
    save_lineup(session, None, team_id, config, league_id)

def copy_league_lineup_to_match(session: Session, match: Match) -> None:
    """Copia al partido la alineación vigente que cada equipo tiene en la liga.
    No hace commit ni flush: lo hace quien la llama"""

    # busco la alineacion de cada equipo que va a jugar el match (hasta ahora, esta guardada asociada solo a su league_id)
    filas_local = get_lineup_entries(session, league_id = match.league_id, team_id = match.team_host_id)
    filas_visitante = get_lineup_entries(session, league_id=match.league_id, team_id=match.team_away_id)

    # recorro cada una de las 12 filas de la alineacion
    for entry in filas_local + filas_visitante:
        session.add(LineupEntry( # y para cada fila guardo una copia (una nueva lineup entry) en la sesion
            match_id=match.match_id,    # lo asocio a su match_id
            team_id=entry.team_id,
            player_id=entry.player_id,
            behavior_id=entry.behavior_id,
            role=entry.role,
            is_starter=entry.is_starter,
        ))

# -------- Validaciones para partidos amistosos y de liga --------
def validate_team_belongs_to_user(session: Session, user_id: int, team_id: int) -> None:
    """403 si team_id no es el equipo del usuario autenticado."""
    user = get_user_by_id(session, user_id)
    # evita que alguien arme un partido con el equipo de otro usuario
    if not user or user.team_id != team_id:
        raise ForbiddenError("El equipo no pertenece al usuario autenticado.")


def validate_match_duration(match_duration: int) -> None:
    """400 INVALID_SETTINGS si la duración no es válida."""
    if match_duration != 2 and match_duration != 5:  
        raise InvalidSettingsError("La duración del partido es inválida")


def validate_min_players(session: Session, team_id: int) -> list:
    """422 PRECONDITION_FAILED si el equipo tiene menos de 6 jugadores. Devuelve los jugadores."""
    team_players = get_players_by_team(session, team_id)
    if len(team_players) < 6:
        raise PreconditionFailedError("El equipo no cumple con el mínimo de jugadores para jugar un partido")
    # devuelvo los jugadores para que validate_lineup no vuelva a consultarlos
    return team_players


# Chequeos de la alineación
def _check_formation_and_roles(config: LineupConfig) -> None:
    """Falla si la formación no existe, si no hay 3 titulares y 3 suplentes,
    o si los roles de los titulares no son justo los de la formación."""
    # la formación tiene que ser una conocida (falla con ej: "9-9")
    if config.formation_type not in FORMATION_ROLES:
        raise InvalidConfigurationError(INVALID_LINEUP_MESSAGE)

    # exactamente 3 titulares y 3 suplentes
    if len(config.starting_players) != STARTERS_COUNT or len(config.substitute_players) != SUBSTITUTES_COUNT:
        raise InvalidConfigurationError(INVALID_LINEUP_MESSAGE)

    # los roles de los titulares: cada rol de la formación tiene que aparecer exactamente una vez
    # (falla si viene repetido, ej: ["DEF_LEFT", "DEF_LEFT", "FORWARD"], o si falta alguno)
    roles = []
    for starter in config.starting_players:
        roles.append(starter.role)
    for rol in FORMATION_ROLES[config.formation_type]:
        if roles.count(rol) != 1:
            raise InvalidConfigurationError(INVALID_LINEUP_MESSAGE)


def _check_players(config: LineupConfig, team_players: list) -> None:
    """Falla si hay jugadores repetidos o que no pertenecen al equipo."""
    # guardo los player_id de titulares y suplentes en una lista
    player_ids = []
    for starter in config.starting_players:
        player_ids.append(starter.player_id)
    for substitute in config.substitute_players:
        player_ids.append(substitute.player_id)

    # los 6 jugadores son distintos (ni repetidos, ni titular y suplente a la vez)
    for player_id in player_ids:
        if player_ids.count(player_id) > 1:
            raise InvalidConfigurationError(INVALID_LINEUP_MESSAGE)

    # los 6 jugadores pertenecen al equipo (falla si algún player_id no existe o es de otro equipo)
    team_player_ids = []
    for player in team_players:
        team_player_ids.append(player.player_id)
    for player_id in player_ids:
        if player_id not in team_player_ids:
            raise InvalidConfigurationError("Los jugadores seleccionados no pertenecen al equipo del usuario autenticado")


def _check_behaviors(session: Session, config: LineupConfig, user_id: int) -> None:
    """Falla si algún behavior_id no existe, el usuario no puede usarlo o es de DT (COACH):
    en una alineación solo van comportamientos de jugador (PLAYER)."""
    # guardo todos los behavior_id de titulares y suplentes en una lista (pueden venir repetidos)
    behavior_ids = []
    for starter in config.starting_players:
        behavior_ids.append(starter.behavior_id)
    for substitute in config.substitute_players:
        behavior_ids.append(substitute.behavior_id)

    # la función solo devuelve los comportamientos que existen, los ids que no existan no vienen
    behaviors = get_behaviors_by_ids(session, behavior_ids)
    # me quedo solo con los ids que el usuario puede usar y que son de jugador
    # (un COACH queda afuera, así se rechaza con el mismo error que un comportamiento no válido)
    usable_ids = []
    for behavior in behaviors:
        if behavior.behavior_type == BehaviorType.PLAYER and (behavior.is_default or behavior.user_id == user_id):
            usable_ids.append(behavior.behavior_id)

    # si alguno de los pedidos no está entre los usables, lo rechazo
    for behavior_id in behavior_ids:
        if behavior_id not in usable_ids:
            raise InvalidConfigurationError("Los comportamientos seleccionados no son válidos para el usuario autenticado")


def validate_lineup(session: Session, config: LineupConfig, team_players: list, user_id: int) -> None:
    """400 INVALID_CONFIGURATION si algo de la alineación está mal."""
    _check_formation_and_roles(config)
    _check_players(config, team_players)
    _check_behaviors(session, config, user_id)