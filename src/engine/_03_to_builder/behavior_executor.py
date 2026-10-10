"""
Ejecución de los comportamientos de los jugadores: convierte el código de
cada comportamiento en una función on_tick y arma el execute_behavior que
usa run_tick.
"""
from src.engine.intentions import Intention
from engine._03_to_builder.player_api import PlayerAPI
from engine._03_to_builder.snapshot import build_player_snapshot
from src.engine.state import MatchState

def make_execute_behavior(codes: dict[int, str]):
    """
    Devuelve un execute_behavior(state, player_id) que retorna una Intention lista para inyectar en run_tick.
    Los codes tienen la forma {behavior_id: code} y se cargan una sola vez, al iniciar el partido 
    """

    # armo mi on_ticks_dict,  donde con load_on_tick convierto cada texto en una funcion
    on_ticks_dict = {} 
    for behavior_id, code in codes.items():
        on_ticks_dict[behavior_id] = load_on_tick(code) # queda de la forma {1: función A, 2: función B, etc}

    def execute_behavior(state: MatchState, player_id: int) -> Intention:
        """
        Corre el comportamiento de UN jugador en UN tick y devuelve lo que
        decidió hacer. run_tick la llama una vez por cada jugador en cancha.
        """

        gs, attrs = build_player_snapshot(state, player_id) # la foto del partido para este jugador y este tick 
        api = PlayerAPI(gs, attrs) # api es un playerAPI nuevo, exclusivo de este jugador y de este tick 

        # busco la funcion (on_tick) del comportamiento asignado a este jugador
        behavior_id = state.players[player_id].behavior_id
        on_tick = on_ticks_dict[behavior_id]

        on_tick(api) # on_tick no ejecuta nada; lo que se decide queda registrado dentro de api (run_to, kick_ball, idle)
        
        return api.intention # devuelvo la intencion que el comportamiento registro en api (o idle si no registro nada)

    # run_tick llama a execute_behavior en cada tick y es quien luego aplica las intenciones
    return execute_behavior


def load_on_tick(code: str):
    """
    Convierte el texto de un comportamiento en su función on_tick
    """
    
    namespace = {}
    # exec ejecuta el texto del comportamiento como si fuera código Python.
    exec(code, namespace)  # ese texto contiene `def on_tick(api): ...`, y al ejecutarse queda guardado en namespace

    # lanzo error si on tick no existe o no es callable
    if "on_tick" not in namespace or not callable(namespace["on_tick"]):
        raise ValueError("El comportamiento no define una funcion on_tick")
   
    return namespace["on_tick"] # namespace["on_tick"] es la función que definía el codigo


