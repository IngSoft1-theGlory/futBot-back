"""
Estado en memoria del partido en curso.

Hay dos niveles de estado:
  - MatchState: el estado global del partido (equipos, pelota, marcador,
    ticks). Es mutable: match_runner lo actualiza tick a tick.
  - GameState: la foto que ve UN jugador en un tick (en data_types.py)

Ver más info. en Documentación - "ABOUT_DESIGN"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable

from src.schemas.lineup_config import LineupConfig
from src.engine._01_to_world.metrics import PauseType
from src.engine._01_to_world.pitch import BALL_INITIAL_POSITION, TeamSide, starter_position
from src.engine._01_to_world.data_types import Point2D, Vector2D, AttributeType, ActionType
from src.schemas.lineup_config import LineupConfig

# ====== Estado del partido ======

class MatchPhase(Enum):
    """
    Fase del partido dentro del motor, en memoria: IN_PROGRESS, PAUSED o FINISHED.

    No es MatchStatus (src.models.match), que es el estado guardado en la
    base. Primero el motor pone MatchPhase.FINISHED y después se guarda
    MatchStatus.FINISHED.
    """
    IN_PROGRESS = "IN_PROGRESS"
    PAUSED = "PAUSED"
    FINISHED = "FINISHED"


@dataclass
class Score:
    """Goles convertidos por cada equipo (home = anfitrión, away = visitante)."""
    home: int = 0
    away: int = 0
    # añado goles de penales. por defecto es None por si es un amistoso o liga sin penales 
    phome: Optional[int] = None
    paway: Optional[int] = None


@dataclass
class BallState:
    """Posición y velocidad de la pelota. La velocidad es por segundo, no por tick."""
    position: Point2D
    velocity: Vector2D


@dataclass
class MatchPlayerState:
    """
    Estado de un jugador dentro del partido.
    Los suplentes no estan en cancha: para ellos, position, role e initial_position son None.
    """
    player_id: int
    team_id: int
    side: TeamSide  # lado de la cancha que defiende
    is_starter: bool
    role: Optional[str]
    behavior_id: Optional[int]
    position: Optional[Point2D] = None
    current_action: ActionType = ActionType.IDLE
    attributes: dict[AttributeType, int] = field(default_factory=dict)  # default_factory para que cada jugador tenga su propio dict (mutable)
    initial_position: Optional[Point2D] = None  # Donde el jugador arrancó el partido, y a donde vuelve tras un gol (ver simulation._reset_after_goal)
    on_tick: Optional[Callable] = None # para que cada jugador guarde su propia funcion
    is_goalkeeper: bool = False  # True si ataja: la pelota que pasa cerca de él se frena (ver simulation._move_ball)


@dataclass
class PauseState:
    """
    La pausa en curso. Se crea una nueva en cada pausa y vuelve a None al terminar,
    así substituted_team_ids (equipos que ya hicieron su cambio) arranca vacío solo.
    """
    type: PauseType # Cooling Break o Half-Time
    number: int     # 1, 2 o 3
    ends_at: float  # instante de fin, medido con time.monotonic(, pues es un reloj que solo avanza y no se ve afectado por cambios de la hora del sistema.
    substituted_team_ids: set[int] = field(default_factory=set) # IDs de los equipos que ya hicieron su cambio en esta pausa. Se vacía al terminar la pausa.


@dataclass
class MatchState:
    """
    Estado global de un partido en curso.
    current_tick cuenta los ticks ya jugados: el partido termina al llegar a total_ticks.
    """
    match_id: int
    phase: MatchPhase
    current_tick: int
    total_ticks: int
    score: Score
    ball: BallState

    # field(default_factory=dict) y no '= {}': asi cada partido tiene su propio dict de jugadores
    players: dict[int, MatchPlayerState] = field(default_factory=dict)

    # La pausa en curso, o None si el partido no está en pausa.
    pause: Optional[PauseState] = None

    # agrego modo penales para partidos de liga. por defecto es false
    penalties_enabled: bool = False

    def players_of(self, team_id: int) -> list[MatchPlayerState]:
        """Jugadores del equipo, titulares y suplentes."""
        return [p for p in self.players.values() if p.team_id == team_id]

    def on_pitch_player_ids(self) -> list[int]:
        """IDs de los jugadores actualmente en cancha (no en el banco)."""
        return [pid for pid, p in self.players.items() if p.position is not None]


# ====== Registro de partidos en curso ======

class MatchRegistry:
    """
    Diccionario en memoria de los partidos en curso: {match_id: MatchState}.

    Hay una instancia única (match_registry) que comparten el motor, que
    agrega y quita partidos, y los endpoints que consultan el estado en
    vivo (por ejemplo GET /matches/{match_id}/state).
    """
    def __init__(self) -> None:
        self._matches: dict[int, MatchState] = {}

    def add(self, state: MatchState) -> None:
        """Registra el partido. ValueError si ya hay uno con ese match_id."""
        if state.match_id in self._matches:
            raise ValueError(f"Ya existe un estado en memoria para match_id={state.match_id}")
        self._matches[state.match_id] = state

    def get(self, match_id: int) -> Optional[MatchState]:
        """El estado del partido, o None si no está en curso."""
        return self._matches.get(match_id)

    def remove(self, match_id: int) -> None:
        self._matches.pop(match_id, None)

    def __contains__(self, match_id: int) -> bool:
        return match_id in self._matches


match_registry = MatchRegistry()


# ====== Construcción del estado inicial ======

class MatchInitializationError(Exception):
    """
    El estado inicial no se pudo construir de forma consistente.

    No es un AppError a propósito: el motor no sabe de HTTP. Quien
    arranca el partido la captura y la traduce al error que corresponda.
    """


@dataclass(frozen=True)
class TeamMatchSetup:
    """
    Lo que aporta un equipo al armar el estado inicial: su lineup y los atributos de cada jugador.
    """
    team_id: int
    side: TeamSide
    lineup: LineupConfig
    attributes: dict[int, dict[AttributeType, int]]  # player_id -> atributos


def attributes_of(player) -> dict[AttributeType, int]:
    """
    Pasa los atributos de un jugador de la base al dict que usa el motor.

    'player' es cualquier objeto con power, agility, control, speed y
    strength, asi el motor no necesita importar el modelo Player.
    """
    return {
        AttributeType.POWER: player.power,
        AttributeType.AGILITY: player.agility,
        AttributeType.CONTROL: player.control,
        AttributeType.SPEED: player.speed,
        AttributeType.STRENGTH: player.strength,
    }


def build_initial_state(
    match_id: int,
    total_ticks: int,
    home: TeamMatchSetup,
    away: TeamMatchSetup,
    penalties_enabled: bool = False,
) -> MatchState:
    """
    Arma el MatchState inicial: tick = 0, marcador 0-0, pelota en
    el centro, titulares en su posicion de formacion y suplentes fuera de la cancha.
    Lanza MatchInitializationError si los datos son inconsistentes.
    """
    if home.team_id == away.team_id:
        raise MatchInitializationError("Los dos equipos participantes no pueden ser el mismo equipo.")
    if home.side == away.side:
        raise MatchInitializationError("Los dos equipos no pueden defender el mismo lado de la cancha.")
    if total_ticks <= 0:
        raise MatchInitializationError(f"total_ticks debe ser positivo (recibido: {total_ticks}).")

    players = _build_player_states(home)
    players.update(_build_player_states(away))

    return MatchState(
        match_id=match_id,
        phase=MatchPhase.IN_PROGRESS,
        current_tick=0,
        total_ticks=total_ticks,
        score=Score(home=0, away=0),
        ball=BallState(position=BALL_INITIAL_POSITION, velocity=Vector2D(0.0, 0.0)),
        players=players,
        penalties_enabled=penalties_enabled,
    )


def _build_player_states(setup: TeamMatchSetup) -> dict[int, MatchPlayerState]:
    """
    Arma los MatchPlayerState de un equipo, por player_id.
    Los titulares se ubican en cancha según su formación, rol y lado; los suplentes quedan afuera.
    """
    players = {}
    for starter in setup.lineup.starting_players:
        start = starter_position(setup.lineup.formation_type, starter.role, setup.side)
        players[starter.player_id] = MatchPlayerState(
            player_id=starter.player_id, team_id=setup.team_id, side=setup.side,
            is_starter=True, role=starter.role, behavior_id=starter.behavior_id,
            position=start,
            attributes=_copy_attributes(setup, starter.player_id),
            initial_position=start,
        )
    for substitute in setup.lineup.substitute_players:
        players[substitute.player_id] = MatchPlayerState(
            player_id=substitute.player_id, team_id=setup.team_id, side=setup.side,
            is_starter=False, role=None, behavior_id=substitute.behavior_id,
            attributes=_copy_attributes(setup, substitute.player_id),
        )

    return players


def _copy_attributes(setup: TeamMatchSetup, player_id: int) -> dict[AttributeType, int]:
    """Copia de los atributos del jugador. Lanza MatchInitializationError si el setup no los trae."""
    if player_id not in setup.attributes:
        raise MatchInitializationError(f"Faltan los atributos del jugador {player_id}.")
    return dict(setup.attributes[player_id])  # copia: cada jugador tiene su propio dict

# ====== Sustitución de jugadores ======

class SubstitutionError(Exception):
    """
    Base de los errores de sustitución.

    No es un AppError a propósito (igual que MatchInitializationError): el motor
    no sabe de HTTP. El endpoint de sustitución los captura y los traduce.
    """


class NotInPauseError(SubstitutionError):
    """El partido no está en una pausa."""


class InvalidSubstitutionError(SubstitutionError):
    """Los jugadores no sirven para el cambio (ver substitute_player)."""


class SubstitutionLimitError(SubstitutionError):
    """El equipo ya hizo su cambio en esta pausa."""


def substitute_player(state: MatchState, team_id: int, player_out_id: int, player_in_id: int) -> None:
    """
    Cambia un titular (player_out) por un suplente (player_in) del mismo equipo.
    Modifica state directamente y no devuelve nada.

    Valida en este orden (el orden importa: es el que fija qué error se lanza
    cuando hay más de un problema a la vez):
      1. Hay pausa                           -> Caso contrario: NotInPauseError
      2. Los jugadores sirven para el cambio -> Caso contrario: InvalidSubstitutionError
      3. El equipo no cambió en esta pausa   -> Caso contrario:SubstitutionLimitError

    Es síncrona y sin await a propósito: el chequeo del límite y el cambio son
    una sola operación, así dos pedidos casi simultáneos no pueden pasar los dos.
    """

    # 1) Solo se puede cambiar durante una pausa: fuera de ella, state.pause es None.
    if state.pause is None:
        raise NotInPauseError("Solo se puede hacer un cambio durante una pausa.")

    # 2) Los dos jugadores tienen que existir y ser del equipo; el saliente tiene que
    #    estar en cancha y el entrante en el banco. "En cancha" = tener position
    #    el mismo criterio que on_pitch_player_ids.
    player_out = state.players.get(player_out_id)
    player_in = state.players.get(player_in_id)
    if (
        player_out is None or player_in is None
        or player_out.team_id != team_id or player_in.team_id != team_id
        or player_out.position is None      # el saliente tiene que estar en cancha
        or player_in.position is not None   # el entrante tiene que estar en el banco
    ):
        raise InvalidSubstitutionError("Cambio inválido: el saliente debe estar en cancha y el entrante en el banco, ambos del equipo.")

    # 3) Un solo cambio por equipo en cada pausa. state.pause es un objeto nuevo en
    #    cada pausa, así que substituted_team_ids arranca vacío solo: no hay que limpiarlo.
    if team_id in state.pause.substituted_team_ids:
        raise SubstitutionLimitError("El equipo ya hizo su cambio en esta pausa.")

    # Todo validado: recién ahora se modifica el estado. Si algo falla arriba, no se toca nada.

    # El entrante ocupa el lugar del saliente: mismo rol y misma posición.
    # Sus attributes y behavior_id no se tocan: ya los trae cargados (los suplentes también).
    player_in.position = player_out.position
    player_in.role = player_out.role
    player_in.initial_position = player_out.initial_position
    player_in.is_starter = True

    # El saliente vuelve al banco: queda como un suplente más (sin posición ni rol).
    player_out.position = None
    player_out.role = None
    player_out.initial_position = None
    player_out.is_starter = False
    player_out.current_action = ActionType.IDLE  # no queda con la acción del último tick que jugó

    # Se anota el cambio para bloquear el segundo del equipo en esta pausa.
    state.pause.substituted_team_ids.add(team_id)
