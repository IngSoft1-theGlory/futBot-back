# src/engine/snapshot.py

from src.engine.game_types import GameState, AttributeType
from src.engine.state import MatchState
from src.engine.pitch import goal_center, opponent_goal_center

def build_player_snapshot(match_state: MatchState, player_id: int) -> tuple[GameState, dict[AttributeType, int]]:
    """Construye una instantánea del juego para un jugador específico."""

    # obtengo el jugador como un matchPlayerState
    player = match_state.players[player_id] 

    # obtengo a sus compañeros de equipo que son titulares en el partido
    teammates = match_state.players_of(player.team_id)  
    teammates_positions = []
    for t in teammates:
        if t.player_id != player.player_id and t.position is not None:
            teammates_positions.append(t.position)   # guardo la posicion, no el jugador, porque gamestate tiene las posiciones

    # idem con los rivales
    rivals_positions = [] 
    for p in match_state.players.values():
        if p.team_id != player.team_id and p.position is not None:
            rivals_positions.append(p.position) 

    # armo los arcos segun el equipo del jugador
    team_goal = goal_center(player.side) 
    rivals_goal = opponent_goal_center(player.side)

    # armo el GameState, con copias de las listas
    return GameState(
        ball_position = match_state.ball.position, 
        ball_velocity = match_state.ball.velocity,  
        my_position = player.position,  
        teammates = list(teammates_positions), # se devuelve una copia para que mutarlos no afecte
        opponents = list(rivals_positions),      # a otros jugadores ni al estado del motor
        team_goal = team_goal, 
        opponent_goal = rivals_goal,
    ), player.attributes




