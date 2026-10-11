"""
Ejecución de los comportamientos de los jugadores: convierte el código de
cada comportamiento en una función on_tick y arma el execute_behavior que
usa run_tick.
"""

from src.engine.intentions import Intention
from src.engine.player_api import PlayerAPI
from src.engine.snapshot import build_player_snapshot
from src.engine._02_to_match.state import MatchState


def make_execute_behavior(codes: dict[int, str]):
    """
    Devuelve un execute_behavior(state, player_id) que retorna una Intention lista para inyectar en run_tick.

    Los codes tienen la forma {behavior_id: code} y se cargan una sola vez, al iniciar el partido 
    """
    
    # armo mi on_ticks_dict,  donde con load_on_tick convierto cada texto en una funcion
    # queda de la forma {1: función A, 2: función B, etc}
    on_ticks_dict = {} 
    for behavior_id, code in codes.items():
        on_ticks_dict[behavior_id] = load_on_tick(code)

    def execute_behavior(state: MatchState, player_id: int) -> Intention:
        """
        Corre el comportamiento de UN jugador en UN tick y devuelve lo que
        decidió hacer. run_tick la llama una vez por cada jugador en cancha.
        """

        # la foto del partido para este jugador y este tick 
        # los comportamientos no pueden modificar el estado real del partido 
        gs, attrs = build_player_snapshot(state, player_id)

        # api es un playerAPI nuevo, exclusivo de este jugador y de este tick
        # es lo unico que el comportamiento ve del partido
        api = PlayerAPI(gs, attrs)

        # busco la funcion (on_tick) del comportamiento asignado a este jugador
        behavior_id = state.players[player_id].behavior_id
        on_tick = on_ticks_dict[behavior_id]

        # ejecuto el comportamiento. on_tick no devuelve nada: lo que
        # decide queda registrado dentro de api (run_to, kick_ball, idle)
        on_tick(api) # si on_tick falla, run_tick lo maneja devolviendo IDLE

        # devuelvo la intencion q el comportamiento registro en api
        # idle si no registro nada
        return api.intention  

    # run_tick llama a execute_behavior en cada tick y es quien luego aplica las intenciones
    return execute_behavior


def load_on_tick(code: str):
    """
    Convierte el texto de un comportamiento en su función on_tick
    """

    namespace = {}
  
    # exec ejecuta el texto del comportamiento como si fuera código Python.
    # ese texto contiene `def on_tick(api): ...`, y al ejecutarse queda
    # guardado en namespace
    exec(code, namespace) 

    # lanzo error si on tick no existe o no es callable
    if "on_tick" not in namespace or not callable(namespace["on_tick"]):
        raise ValueError("El comportamiento no define una funcion on_tick")  # quien arme el partido debe capturar esta excepcion y traducirla al error q corresponda

    # namespace["on_tick"] es la función que definía el codigo
    return namespace["on_tick"]


