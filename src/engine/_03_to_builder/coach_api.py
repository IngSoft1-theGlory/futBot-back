"""
CoachAPI: interfaz que ve el comportamiento del director técnico (DT) en on_tick.

A diferencia de PlayerAPI, no registra intenciones: el DT actúa solo y entre ticks,
así que cada primitiva modifica el estado del partido en el momento. Son síncronas
(sin await) y no llaman a ningún endpoint: trabajan directo sobre el MatchState.
El DT solo puede actuar sobre su propio equipo.
"""

from src.engine._02_to_match.state import MatchState, substitute_player
from src.engine._03_to_builder.behavior_executor import assign_behavior
from typing import Optional


class CoachAPI:
    """
    Interfaz inyectada por el servidor al on_tick del DT. Cada instancia pertenece a un equipo.
    """

    def __init__(self, state: MatchState, team_id: int, behavior_codes: dict[int, str]):
        self._state = state
        self._team_id = team_id
        # {behavior_id: código} de los comportamientos que el DT puede usar.
        # El motor no consulta la base: los códigos ya vienen cargados.
        self._behavior_codes = behavior_codes

    # =========================== Lectura ===========================

    def get_current_tick(self) -> int:
        """Devuelve el tick actual del partido."""
        return self._state.current_tick

    def get_pause_type(self) -> Optional[str]:
        """Devuelve el tipo de pausa ("COOLING_BREAK" o "HALF_TIME"), o None si no hay pausa."""
        if self._state.pause is None:
            return None
        return self._state.pause.type.value  # str y no PauseType: el código del DT no puede importar el Enum

    def get_starters(self) -> list[int]:
        """IDs de los titulares del equipo (en cancha), en orden de alineación."""
        # players_of respeta el orden de la alineación. "En cancha" = tener position,
        # el mismo criterio que usa substitute_player.
        return [p.player_id for p in self._state.players_of(self._team_id) if p.position is not None]

    def get_substitutes(self) -> list[int]:
        """IDs de los suplentes del equipo (en el banco), en orden de alineación."""
        return [p.player_id for p in self._state.players_of(self._team_id) if p.position is None]

    # =========================== Acción ===========================

    def change_behavior(self, player_id: int, behavior_id: int) -> None:
        """
        Cambia el comportamiento de un titular del equipo del DT.

        Lanza ValueError si el comportamiento no está entre los que el DT puede usar
        o si el jugador no existe, es de otro equipo o no es titular. Si el código del
        comportamiento no carga, el error de assign_behavior sale sin capturarse y el
        jugador conserva el que tenía.
        """
        if behavior_id not in self._behavior_codes:
            raise ValueError(f"El comportamiento {behavior_id} no está entre los que el DT puede usar.")

        # Titular = en cancha (tener position), el mismo criterio que get_starters.
        player = self._state.players.get(player_id)
        if player is None or player.team_id != self._team_id or player.position is None:
            raise ValueError(f"El jugador {player_id} no es un titular del equipo del DT.")

        assign_behavior(player, behavior_id, self._behavior_codes[behavior_id])

    def substitute(self, player_out_id: int, player_in_id: int) -> None:
        """
        Cambia al titular player_out por el suplente player_in.

        No valida nada propio: los errores de substitute_player (NotInPauseError,
        InvalidSubstitutionError, SubstitutionLimitError) salen tal cual.
        """
        substitute_player(self._state, self._team_id, player_out_id, player_in_id)