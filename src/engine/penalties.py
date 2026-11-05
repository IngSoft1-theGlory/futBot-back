"""
Tanda de penales: preparación.

prepare_shootout sortea, para cada equipo, el orden en que patean y el orden
en que atajan sus titulares, así como dejar el marcador de penales en 0-0.
"""

from __future__ import annotations

import random

from src.engine._02_to_match.state import MatchState, PenaltyShootout

from src.engine._01_to_world.data_types import Point2D, Vector2D
from src.engine._01_to_world.pitch import (
    PENALTY_BALL_GAP, PENALTY_DISTANCE, TeamSide, goal_center, opposite_side,
)
from src.penalty_behaviors import assign_penalty_goalkeeper, assign_penalty_kicker

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

def prepare_turn(state, kicker_team_id, keeper_team_id, round_index) -> None:
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

    # Solo el pateador y el arquero juegan el turno: los demás salen de la cancha
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