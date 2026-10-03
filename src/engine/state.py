"""
Estado interno del partido en memoria.

Dos niveles de estado, para no confundirlos:
  - GameState (src.engine.game_types): la FOTO que ve UN jugador en un
    tick (inmutable; la arma el ticket del snapshot/GameState por
    jugador -- todavía no implementado acá).
  - MatchState (acá): el estado GLOBAL del partido completo -- los dos
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

from src.engine.geometry_types import Point2D, Vector2D
from src.engine.intentions import ActionType
from src.engine.pitch import BALL_INITIAL_POSITION, FORMATION_POSITIONS, TeamSide, starter_position

STARTERS_PER_TEAM = 3
SUBSTITUTES_PER_TEAM = 3


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
    is_starter: bool
    role: Optional[str]  # None en suplentes
    behavior_id: Optional[int]
    position: Optional[Point2D] = None  # None = en el banco
    current_action: ActionType = ActionType.IDLE


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

@dataclass(frozen=True)
class LineupPlayer:
    """
    Una fila de LineupEntry, pero sin SQLAlchemy: el motor no debe
    importar el modelo persistente (no sabe de la base de datos).
    Quien arma el partido (el service, ya con los datos consultados)
    traduce las filas reales de la DB a esto antes de llamar a
    build_initial_state.
    """

    player_id: int
    is_starter: bool
    role: Optional[str]  # None en suplentes
    behavior_id: Optional[int]


@dataclass(frozen=True)
class TeamMatchSetup:
    """Lo que un equipo aporta al armar el estado inicial: su lineup
    completa (6 filas: 3 titulares + 3 suplentes) y la formación con
    la que entra a jugar."""

    team_id: int
    formation_type: str
    side: TeamSide
    players: list[LineupPlayer]


def _validate_team_setup(setup: TeamMatchSetup) -> None:
    starters = [p for p in setup.players if p.is_starter]
    substitutes = [p for p in setup.players if not p.is_starter]

    if len(starters) != STARTERS_PER_TEAM or len(substitutes) != SUBSTITUTES_PER_TEAM:
        raise MatchInitializationError(
            f"El equipo {setup.team_id} no tiene {STARTERS_PER_TEAM} titulares "
            f"y {SUBSTITUTES_PER_TEAM} suplentes (tiene {len(starters)} y {len(substitutes)})."
        )

    if setup.formation_type not in FORMATION_POSITIONS:
        raise MatchInitializationError(
            f"Formación desconocida para el equipo {setup.team_id}: {setup.formation_type!r}"
        )

    expected_roles = set(FORMATION_POSITIONS[setup.formation_type])
    starter_roles = [p.role for p in starters]

    if any(role is None for role in starter_roles):
        raise MatchInitializationError(f"Un titular del equipo {setup.team_id} no tiene rol asignado.")

    if set(starter_roles) != expected_roles:
        raise MatchInitializationError(
            f"Los roles de los titulares del equipo {setup.team_id} ({set(starter_roles)}) "
            f"no corresponden a la formación {setup.formation_type!r} (esperados: {expected_roles})."
        )

    if any(p.role is not None for p in substitutes):
        raise MatchInitializationError(f"Un suplente del equipo {setup.team_id} tiene rol asignado.")

    if any(p.behavior_id is None for p in setup.players):
        raise MatchInitializationError(
            f"Un jugador del equipo {setup.team_id} no tiene comportamiento asignado."
        )

    player_ids = [p.player_id for p in setup.players]
    if len(set(player_ids)) != len(player_ids):
        raise MatchInitializationError(f"El equipo {setup.team_id} tiene un jugador repetido en la alineación.")


def _build_player_states(setup: TeamMatchSetup) -> dict[int, MatchPlayerState]:
    players: dict[int, MatchPlayerState] = {}
    for lineup_player in setup.players:
        position = None
        if lineup_player.is_starter:
            position = starter_position(setup.formation_type, lineup_player.role, setup.side)

        players[lineup_player.player_id] = MatchPlayerState(
            player_id=lineup_player.player_id,
            team_id=setup.team_id,
            is_starter=lineup_player.is_starter,
            role=lineup_player.role,
            behavior_id=lineup_player.behavior_id,
            position=position,
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

    _validate_team_setup(home)
    _validate_team_setup(away)

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
