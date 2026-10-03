"""
PlayerAPI: interfaz que ve el comportamiento en on_tick.
Los getters leen de un snapshot ya armado (no consultan la base de datos).
Las primitivas de acción solo registran una Intention.
"""

import math

from src.engine.game_types import AttributeType, GameState
from src.engine.geometry_types import Point2D
from src.engine.intentions import ActionType, Intention
from src.engine.constants import reach_distance


def _is_finite_number(value) -> bool:
    """True si `value` es un int o float común (no NaN, no infinito, no bool)."""
    # bool se excluye a propósito: en Python True es un int (True == 1).
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


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

    def run_to(self, target: Point2D, speed_percentage: float) -> None:
        """
        lo que hace es registrar la intencion de correr en linea recta hacia `target`
        osea hacia una posicion (x,y)
        Point2D es el destino encoordenadas finitas
        speed_percentage es que porcentaje de su velocidad máxima usa,
               entre 0.1 (practicamente no se mueve) y 1.0 (a fondo).

        solo REGISTRA la intencion: el movimiento real lo calcula resolve (osea em resolve.py)

        argumentos invalidos: lanza ValueError y deja la intención en IDLE
        Si on_tick no atrapa el error, el motor (match_runner.run_tick) lo
        atrapa y le asigna IDLE al jugador; si on_tick lo atrapa y sigue,
        el jugador igual queda en IDLE, salvo que llame a otra primitiva.
        """
        # primero se descarta cualquier intencion anterior: si los argumentos son invalidos, el jugador queda quieto este tick.
        self._intention = Intention(ActionType.IDLE)

        if not isinstance(target, Point2D):
            raise ValueError(f"run_to: target debe ser un Point2D (recibido: {target!r}).")
        if not (_is_finite_number(target.x) and _is_finite_number(target.y)):
            raise ValueError(f"run_to: target debe tener coordenadas finitas (recibido: {target!r}).")
        if not _is_finite_number(speed_percentage):
            raise ValueError(
                f"run_to: speed_percentage debe ser un número finito (recibido: {speed_percentage!r})."
            )
        if not 0.0 <= speed_percentage <= 1.0:
            raise ValueError(
                f"run_to: speed_percentage debe estar entre 0.0 y 1.0 (recibido: {speed_percentage!r})."
            )

        self._intention = Intention(
            ActionType.RUN_TO,
            target=target,
            speed_percentage=float(speed_percentage),
        )

    # --- Lectura por parte del motor ---

    @property
    def intention(self) -> Intention:
        """Intención registrada en este tick (IDLE por defecto)."""
        return self._intention
