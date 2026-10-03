"""
resolve: función pura que aplica una Intention a un GameState.
"""

from src.engine.game_types import GameState
from src.engine.intentions import ActionType, Intention


def resolve(state: GameState, intention: Intention) -> GameState:
    """
    Devuelve el GameState resultante de aplicar `intention`.
    Por ahora solo IDLE (estado sin cambios). run_to y kick_ball sin implementar; 
    hasta entonces fallan fuerte para que nadie crea que están implementadas.
    """
    if intention.action == ActionType.IDLE:
        return state
    raise NotImplementedError(f"Acción no implementada: {intention.action}")
