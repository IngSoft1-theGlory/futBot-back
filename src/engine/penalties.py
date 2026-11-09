"""
Tanda de penales.

- prepare_shootout sortea, para cada equipo, el orden en que patean y el orden
  en que atajan sus titulares, así como dejar el marcador de penales en 0-0.
- prepare_turn ubica al pateador, al arquero y la pelota de un penal.
- play_shootout juega la tanda completa ronda a ronda (la llama run_match).
- play_penalty juega un solo penal, hasta que hay gol o se agotan los ticks.
"""

from __future__ import annotations

import asyncio
import logging
import random

from src.engine._01_to_world.metrics import PENALTY_MAX_ROUNDS, PENALTY_MAX_TICKS, PENALTY_PAUSE_SECONDS
from src.engine._02_to_match.state import MatchState, PenaltyShootout
from src.engine.match_runner import ApplyIntentions, DetectGoal, ExecuteBehavior, NotifyTick, play_tick

from src.engine._01_to_world.data_types import Point2D, Vector2D
from src.engine._01_to_world.pitch import (
    PENALTY_BALL_GAP, PENALTY_DISTANCE, TeamSide, goal_center, opposite_side,
)
from src.penalty_behaviors import assign_penalty_goalkeeper, assign_penalty_kicker

logger = logging.getLogger(__name__)

# Los penales se patean siempre en el arco izquierdo (x=0).
PENALTY_GOAL_SIDE = TeamSide.HOME


def prepare_shootout(state: MatchState) -> None:
    """
    Prepara la tanda de penales del partido. Se sortea una sola vez: si la
    tanda ya está preparada, no hace nada y el orden no cambia.
    """
    # Un pedido repetido no reinicia nada
    if state.penalty_shootout is not None and state.penalty_shootout.prepared:
        return

    shootout = PenaltyShootout()
    team_ids = {player.team_id for player in state.players.values()}
    for team_id in team_ids:
        # Solo los titulares patean y atajan: los suplentes quedan afuera
        starters = [p.player_id for p in state.players_of(team_id) if p.is_starter]
        # El orden de pateo y el de atajada se sortean por separado
        shootout.kicker_order[team_id] = random.sample(starters, len(starters))
        shootout.keeper_order[team_id] = random.sample(starters, len(starters))

    shootout.prepared = True
    state.penalty_shootout = shootout

    # El marcador de penales arranca en 0-0
    state.score.phome = 0
    state.score.paway = 0

def prepare_turn(state: MatchState, kicker_team_id: int, keeper_team_id: int, round_index: int) -> None:
    """
    Prepara un turno de la tanda: un equipo patea y el otro ataja.
    Toma del orden sorteado por prepare_shootout al pateador de kicker_team_id y al
    arquero del otro equipo, ambos en la posición round_index de su lista (0 = primera ronda).
    Solo esos dos quedan en cancha; el arquero en el arco izquierdo, el pateador a
    PENALTY_DISTANCE de ese arco y la pelota quieta entre ambos. Cada uno recibe su
    comportamiento, que reemplaza al del turno anterior.
    """
    shootout = state.penalty_shootout
    kicker = state.players[shootout.kicker_order[kicker_team_id][round_index]]
    keeper = state.players[shootout.keeper_order[keeper_team_id][round_index]]

    # Inyección de Comportamientos primero: si alguno fallara, no queda el estado a medias.
    # assign_* pisa on_tick, behavior_id e is_goalkeeper, así un jugador que fue
    # pateador y ahora ataja (o al revés) queda solo con el comportamiento nuevo.
    assign_penalty_kicker(kicker)
    assign_penalty_goalkeeper(keeper)

    # Se saca de la cancha a TODOS los jugadores (position = None es "fuera de la cancha"), 
    # incluidos el pateador y el arquero. Más abajo a esos dos se les vuelve a dar una posición, 
    # así que al terminar solo ellos quedan en cancha.
    for player in state.players.values():
        player.position = None

    # Se fija la posición del arco a defender.
    goal = goal_center(PENALTY_GOAL_SIDE)

    # Así como los lados tanto del arquero como del pateador.
    keeper.side = PENALTY_GOAL_SIDE
    kicker.side = opposite_side(PENALTY_GOAL_SIDE)

    # Se ubica al arquero en el arco y al pateador a PENALTY_DISTANCE de ese arco.
    keeper.position = goal
    kicker.position = Point2D(goal.x + PENALTY_DISTANCE, goal.y)  # el arco está en x=0: la cancha crece hacia +x

    # Se ubica la pelota quieta entre ambos, a PENALTY_BALL_GAP del pateador, del lado del arco.
    state.ball.position = Point2D(kicker.position.x - PENALTY_BALL_GAP, goal.y)
    state.ball.velocity = Vector2D(0.0, 0.0)

def _add_penalty_goal(state: MatchState, team_id: int) -> None:
    """Suma 1 gol de penal al equipo team_id: a phome si es el anfitrión, a paway si es el visitante."""
    if team_id == state.host_team_id:
        state.score.phome += 1
    else:
        state.score.paway += 1

async def play_shootout(
    state: MatchState,
    # '*' Obliga a pasar por nombre lo que viene después, de esta forma cada
    # valor que se pase a la función va a parar a la variable correcta y no se va a confundir con otra.
    # i.e: lo que se asigne en execute_behavior va a parar a la variable execute_behavior y no a otra.
    *,                                  
    execute_behavior: ExecuteBehavior,
    apply_intentions: ApplyIntentions,
    detect_goal: DetectGoal,
    notify: NotifyTick,
    tick_interval_seconds: float,
    penalty_pause_seconds: float = PENALTY_PAUSE_SECONDS,
) -> None:
    """
    Juega la tanda de penales ronda a ronda hasta que haya un ganador. El resultado
    queda en state.score.phome y state.score.paway, y nunca empatado.

    Una ronda es un penal del host y uno del visitante (en ese orden), con un máximo de
    PENALTY_MAX_ROUNDS rondas. Al terminar cada ronda:
      - si convirtió un solo equipo, ese equipo gana y la tanda termina
      - si convirtieron los dos o ninguno, se juega otra ronda
      - si después de todas las rondas siguen empatados, se sortea al ganador
    """
    prepare_shootout(state)  # sortea el orden y deja phome y paway en 0

    host = state.host_team_id
    away = state.away_team_id

    round_index = 0

    # La tanda sigue mientras queden rondas y los equipos estén empatados (arranca 0-0).
    # Al terminar la ronda, si el marcador difiere es porque convirtió un solo equipo: ya hay ganador.

    while round_index < PENALTY_MAX_ROUNDS and state.score.phome == state.score.paway:
        # Entre un penal y el siguiente el estado queda congelado unos segundos,
        # para que se vea cómo terminó el anterior (no hay pausa antes del primero)
        if round_index > 0:
            await asyncio.sleep(penalty_pause_seconds)

        # Patea el host y ataja el visitante
        await _play_penalty(
            state, host, away, round_index,
            execute_behavior=execute_behavior, apply_intentions=apply_intentions,
            detect_goal=detect_goal, notify=notify, tick_interval_seconds=tick_interval_seconds,
        )

        await asyncio.sleep(penalty_pause_seconds)

        # y después patea el visitante y ataja el host
        await _play_penalty(
            state, away, host, round_index,
            execute_behavior=execute_behavior, apply_intentions=apply_intentions,
            detect_goal=detect_goal, notify=notify, tick_interval_seconds=tick_interval_seconds,
        )

        round_index += 1

    # Si siguen empatados es porque se agotaron las rondas: se sortea al ganador y se le suma
    # 1 gol de penal, para que el marcador de penales nunca quede empatado.
    if state.score.phome == state.score.paway:
        _add_penalty_goal(state, random.choice([host, away]))


async def _play_penalty(
    state: MatchState,
    kicker_team_id: int,
    keeper_team_id: int,
    round_index: int,
    *,
    execute_behavior: ExecuteBehavior,
    apply_intentions: ApplyIntentions,
    detect_goal: DetectGoal,
    notify: NotifyTick,
    tick_interval_seconds: float,
) -> None:
    """
    Juega UN penal: ubica a los jugadores y juega ticks hasta que haya gol en el
    arco o pasen PENALTY_MAX_TICKS ticks. El gol se suma al equipo que patea.
    """
    prepare_turn(state, kicker_team_id, keeper_team_id, round_index)

    goal = False
    ticks_played = 0

    # El penal termina cuando hay gol o cuando pasan PENALTY_MAX_TICKS ticks, lo que ocurra primero
    while not goal and ticks_played < PENALTY_MAX_TICKS:
        # Misma lógica que un tick del partido, pero el gol no va al marcador del partido
        scoring_side = play_tick(
            state,
            execute_behavior=execute_behavior,
            apply_intentions=apply_intentions,
            detect_goal=detect_goal,
        )

        # El arco es siempre el de PENALTY_GOAL_SIDE, así que el gol lo mete el lado contrario
        goal = scoring_side == opposite_side(PENALTY_GOAL_SIDE)

        if goal:
            # pero se le suma al equipo que PATEA, no al que "mete el gol" según el lado:
            # el arco es fijo y los dos equipos patean contra él.
            _add_penalty_goal(state, kicker_team_id)

        try:
            await notify(state)  # igual que en el partido: avisa a los clientes después de cada tick
        except Exception:
            logger.exception("notify falló en un penal del partido %s; la tanda sigue.", state.match_id)
        await asyncio.sleep(tick_interval_seconds)

        ticks_played += 1