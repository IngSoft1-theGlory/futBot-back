"""
Estado interno del partido en memoria.

Dos niveles de estado, para no confundirlos:
  - GameState (src.engine.game_types): la FOTO que ve UN jugador en un
    tick.
  - MatchState: el estado GLOBAL del partido completo -- los dos
    equipos, la pelota, el marcador y los ticks. Es MUTABLE: el loop
    del partido (match_runner.py) lo actualiza tick a tick. De acá
    sale el GameState de cada jugador, y es lo que deberían leer tanto
    el evento WS TICK_UPDATE como GET /matches/{matchId}/state.

MatchRegistry guarda un MatchState por match_id en memoria, para que
dos partidos en simultáneo no compartan estado, es parte del criterio de aceptación
del ticket.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.engine.game_types import AttributeType
from src.engine.geometry_types import Point2D, Vector2D
from src.engine.intentions import ActionType
from src.engine.pitch import BALL_INITIAL_POSITION, TeamSide, starter_position
from src.schemas.lineup_config import LineupConfig

class MatchPhase(Enum):
    """
    Fases del motor en memoria. NO confundir con MatchStatus
    (src.models.match): ese es el status PERSISTIDO (incluye PENDING,
    que acá no existe porque el motor arranca recién cuando el partido
    ya está IN_PROGRESS -- con los dos equipos confirmados). Al llegar
    a FINISHED, quien llama al motor traduce a MatchStatus.FINISHED al
    guardar el resultado final en la base.
    """

    IN_PROGRESS = "IN_PROGRESS"
    FINISHED = "FINISHED"


class MatchInitializationError(Exception):
    """
    El estado inicial no se pudo construir de forma consistente.

    A propósito NO es un AppError (src.core.exceptions): el motor no
    sabe de HTTP ni de status codes. Quien invoca build_initial_state
    desde un endpoint o servicio la captura y la traduce al error de
    negocio que corresponda en ese contexto.
    """


@dataclass
class Score:
    home: int = 0
    away: int = 0


@dataclass
class BallState:
    position: Point2D
    velocity: Vector2D


@dataclass
class MatchPlayerState:
    """
    Estado de un jugador dentro del partido.

    position=None significa "no está en cancha" (suplente). Se usa
    None en vez de una coordenada fuera de los límites a propósito:
    así no hay forma de confundir "está en el banco" con "está parado
    en una esquina", y "¿está en cancha?" es simplemente
    `position is not None` (ver MatchState.on_pitch_player_ids).
    """

    player_id: int
    team_id: int
    side: TeamSide # lado de la cancha que defiende ese jugador
    is_starter: bool
    role: Optional[str]  # None en suplentes
    behavior_id: Optional[int]
    position: Optional[Point2D] = None  # None = en el banco
    current_action: ActionType = ActionType.IDLE
    attributes: dict[AttributeType, int]= field(default_factory=dict)  # default_factory para que cada jugador tenga su propio dict (mutable)
    # Posición con la que arrancó el partido: a donde vuelve el jugador tras un
    # gol (ver simulation._reset_after_goal). None en suplentes.
    initial_position: Optional[Point2D] = None

@dataclass
class MatchState:
    match_id: int
    phase: MatchPhase
    current_tick: int
    total_ticks: int
    score: Score
    ball: BallState
    # OJO con los mutable defaults de Python: un `players: dict = {}`
    # acá haría que TODAS las instancias de MatchState compartan el
    # mismo diccionario (se crea una sola vez, cuando se define la
    # clase). field(default_factory=dict) crea un dict nuevo por cada
    # instancia. Es exactamente el bug que rompería el criterio de
    # "dos partidos en simultáneo no comparten estado" -- ver el test
    # de regresión en test_state.py.
    players: dict[int, MatchPlayerState] = field(default_factory=dict)

    def players_of(self, team_id: int) -> list[MatchPlayerState]:
        return [p for p in self.players.values() if p.team_id == team_id]

    def on_pitch_player_ids(self) -> list[int]:
        """IDs de los jugadores actualmente en cancha (no en el banco)."""
        return [pid for pid, p in self.players.items() if p.position is not None]


class MatchRegistry:
    """
    Partidos en curso, por match_id. Pensado como instancia única a
    nivel de módulo (mismo patrón que event_bus en src/realtime), para
    que el motor y los endpoints que consultan el estado en vivo
    (GET /matches/{id}/state, el WS de partido) lean del mismo lugar.
    """

    def __init__(self) -> None:
        self._matches: dict[int, MatchState] = {}

    def add(self, state: MatchState) -> None:
        if state.match_id in self._matches:
            raise ValueError(f"Ya existe un estado en memoria para match_id={state.match_id}")
        self._matches[state.match_id] = state

    def get(self, match_id: int) -> Optional[MatchState]:
        return self._matches.get(match_id)

    def remove(self, match_id: int) -> None:
        self._matches.pop(match_id, None)

    def __contains__(self, match_id: int) -> bool:
        return match_id in self._matches


# Instancia única: el motor y los endpoints que consultan el estado en
# vivo importan este registry ya armado, en vez de crear uno cada uno.
match_registry = MatchRegistry()


# --- Construcción del estado inicial ---
# (ticket "construir estado actual del partido y ubicarlos en cancha")

def attributes_of(player) -> dict[AttributeType, int]:
    """
    Pasa los atributos de un jugador de la base (modelo Player) al dict que
    usa el motor. `player` es cualquier objeto con power, agility, control,
    speed y strength (no se importa el modelo para que el motor no dependa de él).
    """
    return {
        AttributeType.POWER: player.power,
        AttributeType.AGILITY: player.agility,
        AttributeType.CONTROL: player.control,
        AttributeType.SPEED: player.speed,
        AttributeType.STRENGTH: player.strength,
    }


@dataclass(frozen=True)
class TeamMatchSetup:
    """Lo que un equipo aporta al armar el estado inicial: su lineup
    (formación, 3 titulares y 3 suplentes) y los atributos de cada uno.

    Los atributos NO viajan en el LineupConfig (es lo que manda el cliente):
    los carga quien arranca el partido, leyendo la tabla players y usando
    attributes_of. Tiene que haber una entrada por cada player_id del lineup."""

    team_id: int
    side: TeamSide
    lineup: LineupConfig
    attributes: dict[int, dict[AttributeType, int]]  # player_id -> atributos


def _attributes_for(setup: TeamMatchSetup, player_id: int) -> dict[AttributeType, int]:
    """Copia de los atributos del jugador; falla si el setup no los trae."""
    if player_id not in setup.attributes:
        raise MatchInitializationError(f"Faltan los atributos del jugador {player_id}.")
    return dict(setup.attributes[player_id])  # copia: cada jugador tiene su propio dict


def _build_player_states(setup: TeamMatchSetup) -> dict[int, MatchPlayerState]:
    players = {}
    for starter in setup.lineup.starting_players:
        start = starter_position(setup.lineup.formation_type, starter.role, setup.side)
        players[starter.player_id] = MatchPlayerState(
            player_id=starter.player_id, team_id=setup.team_id, side=setup.side,
            is_starter=True, role=starter.role, behavior_id=starter.behavior_id,
            position=start,
            attributes=_attributes_for(setup, starter.player_id),
            initial_position=start,
        )
    for substitute in setup.lineup.substitute_players:
        players[substitute.player_id] = MatchPlayerState(
            player_id=substitute.player_id, team_id=setup.team_id, side=setup.side,
            is_starter=False, role=None, behavior_id=substitute.behavior_id,
            attributes=_attributes_for(setup, substitute.player_id),
        )
    return players


def build_initial_state(
    match_id: int,
    total_ticks: int,
    home: TeamMatchSetup,
    away: TeamMatchSetup,
) -> MatchState:
    """
    Arma el MatchState inicial: current_tick=0, marcador 0-0, pelota en
    el centro de la cancha, titulares ubicados según su formación y
    rol (considerando el lado de cancha de cada equipo), suplentes
    fuera de la cancha (position=None).

    Lanza MatchInitializationError si algo es inconsistente (AC: "la
    inicialización no debe finalizar exitosamente si falta alguno de
    los recursos obligatorios"). Esta función no la captura: es
    responsabilidad de quien arranca el motor no seguir si esto falla
    (AC: "el motor no debe comenzar cuando la inicialización haya
    fallado") -- ver match_runner.run_match, que nunca recibe un
    MatchState si build_initial_state no llegó a devolver uno.

    Lo que esta función NO valida (ya se validó antes, en otra capa):
    que los player_id/behavior_id realmente existan en la base y
    pertenezcan al equipo -- eso es trabajo de lineup_service al
    guardar la alineación, no de este motor.
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
    )
