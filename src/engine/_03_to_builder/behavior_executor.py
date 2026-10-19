"""
Ejecución de los comportamientos de los jugadores.

Convierte el código de un comportamiento en una función on_tick (load_on_tick),
se la guarda a un jugador (assign_behavior) y la corre en cada tick
(execute_behavior). Cada jugador guarda su propia función.
"""

from src.engine._02_to_match.state import MatchState, MatchPlayerState
from src.engine._03_to_builder.snapshot import build_player_snapshot
from src.engine._03_to_builder.player_api import PlayerAPI
from src.engine._01_to_world.data_types import Intention, Point2D, Vector2D
import math 


def execute_behavior(state: MatchState, player_id: int) -> Intention:
    """
    Corre el comportamiento de UN jugador en UN tick y devuelve lo que
    decidió hacer. run_tick la llama una vez por cada jugador en cancha.
    """

    gs, attrs = build_player_snapshot(state, player_id) # la foto del partido para este jugador y este tick 
    api = PlayerAPI(gs, attrs) # api es un playerAPI nuevo, exclusivo de este jugador y de este tick 

    # la funcion on_tick que este jugador tiene guardada
    on_tick = state.players[player_id].on_tick

    on_tick(api) # on_tick no devuelve nada: lo que decide queda registrado dentro de api (run_to, kick_ball, idle, etc)
        
    return api.intention # devuelvo la intencion que el comportamiento registro en api (o idle si no registro nada)


def load_on_tick(code: str):
    """
    Convierte el texto de un comportamiento en su función on_tick
    """
    # Funciones que el comportamiento puede usar. Todo lo que no este aca no esta permitido: no se rechaza al guardar, pero falla al intentar ejecutar
    my_builtins = {"abs": abs, "min": min, "max": max, "len": len, "round": round, "float": float, "int": int, "sum": sum, "bool": bool, "str": str, "list": list, "tuple": tuple, "dict": dict, "any": any, "all": all, "sorted": sorted,} 

    # Nombres disponibles para el código mientras corre. Como no puede hacer import, math, Point2D y Vector2D se le dan ya cargados
    namespace = {"__builtins__": my_builtins, "math": math, "Point2D": Point2D, "Vector2D": Vector2D}

    # exec ejecuta el texto del comportamiento como si fuera código Python.
    exec(code, namespace)  # ese texto contiene `def on_tick(api): ...`, y al ejecutarse queda guardado en namespace

    # lanzo error si on_tick no existe o no es callable
    if "on_tick" not in namespace or not callable(namespace["on_tick"]):
        raise ValueError("El comportamiento no define una funcion on_tick")
   
    return namespace["on_tick"] # namespace["on_tick"] es la función que definía el codigo

def assign_behavior(player: MatchPlayerState, behavior_id: int, code: str) -> None:
    """
    Le asigna un comportamiento a un jugador: guarda su behavior_id y su función on_tick.

    Primero carga el código y recién después modifica al jugador. Si el código
    falla (no compila o no define on_tick), lanza el error y el jugador conserva
    el comportamiento que tenía.
    """
    on_tick = load_on_tick(code) # cargo la funcion del comportamiento 

    # si load_on_tick no lanza error, le asigno el comportamiento al jugador
    player.behavior_id = behavior_id
    player.on_tick = on_tick

