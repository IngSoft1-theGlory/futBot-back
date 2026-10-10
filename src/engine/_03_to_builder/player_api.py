"""
PlayerAPI: interfaz que ve el comportamiento en on_tick.
Los getters leen de un snapshot ya armado. Las primitivas de acción solo registran una Intention.
"""

import math
from src.engine.game_types import AttributeType, GameState
from src.engine.geometry_types import Point2D, Vector2D
from src.engine.intentions import ActionType, Intention
from src.engine.constants import reach_distance

class PlayerAPI:
    """
    Interfaz inyectada por el servidor a on_tick. Cada instancia pertenece a un jugador y a un tick.
    """

    def __init__(self, game_state: GameState, attributes: dict[AttributeType, int]):
        self._game_state = game_state
        self._attributes = attributes
        self._intention = Intention(ActionType.IDLE) # Atributo de INSTANCIA (no de clase): cada PlayerAPI tiene la suya.

    # =========================== Consulta ===========================

    def get_game_state(self) -> GameState:
        """ Devuelve el GameState de este jugador en este tick."""
        return self._game_state

    def get_attribute(self, attribute_name: AttributeType) -> int:
        """ Devuelve el valor del atributo consultado (del snapshot)."""
        return self._attributes[attribute_name]

    def get_reach_distance(self) -> float:
        """ Devuelve la distancia máxima a la que el jugador puede alcanzar la pelota."""
        return reach_distance(self.get_attribute(AttributeType.CONTROL))
    
    # =============== Acción (solo registran intención) ===============

    def idle(self) -> None:
        """ Registra la intención de permanecer detenido en el lugar."""
        self._intention = Intention(ActionType.IDLE)


    def run_to(self, target: Point2D, speed_percentage: float) -> None:
        """
        Registra la intencion de correr en linea recta hacia `target`, es decir, hacia una posicion (x,y).
        
        Ver más info. en Documentación - "ABOUT_DESIGN"
        """

        # primero se descarta cualquier intencion anterior: si los argumentos son invalidos, el jugador queda quieto este tick.
        self._intention = Intention(ActionType.IDLE)

        if not isinstance(target, Point2D):
            raise ValueError(f"run_to: target debe ser un Point2D (recibido: {target!r}).")
        
        if not (_is_finite_number(target.x) and _is_finite_number(target.y)):
            raise ValueError(f"run_to: target debe tener coordenadas finitas (recibido: {target!r}).")
        
        if not _is_finite_number(speed_percentage):
            raise ValueError(f"run_to: speed_percentage debe ser un número finito (recibido: {speed_percentage!r}).")
        
        if not 0.0 <= speed_percentage <= 1.0:
            raise ValueError(f"run_to: speed_percentage debe estar entre 0.0 y 1.0 (recibido: {speed_percentage!r}).")

        self._intention = Intention(
            ActionType.RUN_TO,
            target=target,
            speed_percentage=float(speed_percentage),
        )


    def kick_ball(self, target_direction: Vector2D, power_percentage: float) -> None:
        """
        Registra la intención de patear la pelota en `target_direction`.

        Ver más info. en Documentación - "ABOUT_DESIGN"
        """

        self._intention = Intention(ActionType.IDLE)

        if not isinstance(target_direction, Vector2D):
            raise ValueError(f"kick_ball: target_direction debe ser un Vector2D (recibido: {target_direction!r}).")
        
        if not (_is_finite_number(target_direction.x) and _is_finite_number(target_direction.y)):
            raise ValueError(f"kick_ball: target_direction debe tener componentes finitas (recibido: {target_direction!r}).")
        
        if target_direction.magnitude() == 0: # no hay hacia donde patear
            raise ValueError("kick_ball: target_direction no puede ser el vector cero.")
        
        if not _is_finite_number(power_percentage):
            raise ValueError(f"kick_ball: power_percentage debe ser un número finito (recibido: {power_percentage!r}).")
        
        if not 0.0 <= power_percentage <= 1.0:
            raise ValueError(f"kick_ball: power_percentage debe estar entre 0.0 y 1.0 (recibido: {power_percentage!r}).")

        self._intention = Intention(
            ActionType.KICK_BALL,
            direction=target_direction,
            power_percentage=float(power_percentage),
        )


    # =============== Lectura por parte del motor ===============

    @property
    def intention(self) -> Intention:
        """Intención registrada en este tick (IDLE por defecto)."""
        return self._intention


# =============== Funcion auxiliar =============== 

def _is_finite_number(value) -> bool:
    """True si `value` es un int o float común (no NaN, no infinito, no bool)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)