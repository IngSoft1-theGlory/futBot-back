"""
PlayerAPI: interfaz que ve el comportamiento en on_tick.
Los getters leen de un snapshot ya armado (no consultan la base de datos).
Las primitivas de acción solo registran una Intention.
"""

from src.engine.game_types import AttributeType, GameState
from src.engine.intentions import ActionType, Intention
from src.engine.constants import reach_distance


class PlayerAPI:
    """
    Interfaz inyectada por el servidor a on_tick.

    Política ante llamadas múltiples a primitivas en un mismo tick:
    GANA LA ÚLTIMA llamada (cada primitiva pisa la intención anterior).
    Si on_tick no llama a ninguna primitiva, la intención es IDLE.

    Cada instancia pertenece a un jugador y a un tick.
    """

    def __init__(self, game_state: GameState, attributes: dict[AttributeType, int]):
        self._game_state = game_state
        self._attributes = attributes
        # Atributo de INSTANCIA (no de clase): cada PlayerAPI tiene la suya.
        self._intention = Intention(ActionType.IDLE)

    # --- Consulta ---

    def get_game_state(self) -> GameState:
        """@brief Devuelve el GameState de este jugador en este tick."""
        return self._game_state

    def get_attribute(self, attribute_name: AttributeType) -> int:
        """@brief Devuelve el valor del atributo consultado (del snapshot)."""
        return self._attributes[attribute_name]

    def get_reach_distance(self) -> float:
        """
        @brief Devuelve la distancia máxima a la que el jugador puede alcanzar la pelota.
        """
        return reach_distance(self.get_attribute(AttributeType.CONTROL))
    # --- Acción (solo registran intención) ---

    def idle(self) -> None:
        """@brief Registra la intención de permanecer detenido en el lugar."""
        self._intention = Intention(ActionType.IDLE)

    # --- Lectura por parte del motor ---

    @property
    def intention(self) -> Intention:
        """Intención registrada en este tick (IDLE por defecto)."""
        return self._intention
