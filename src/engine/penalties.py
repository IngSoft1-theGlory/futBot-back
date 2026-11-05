"""
Tanda de penales: preparación.

prepare_shootout sortea, para cada equipo, el orden en que patean y el orden
en que atajan sus titulares, así como dejar el marcador de penales en 0-0.
"""

from __future__ import annotations

import random

from src.engine._02_to_match.state import MatchState, PenaltyShootout


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