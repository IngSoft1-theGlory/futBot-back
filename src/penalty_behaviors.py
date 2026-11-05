"""
Comportamientos que usa el sistema en los penales.

A diferencia de default_behaviors.py, estos NO se guardan en la base: no tienen
behavior_id y no aparecen en GET /behaviors. Se le asignan directo al jugador
en memoria, durante el partido.
"""

from src.engine._02_to_match.state import MatchPlayerState
from src.engine._03_to_builder.behavior_executor import assign_behavior

# Arquero: corre de un poste al otro, de lado a lado del arco, usando solo run_to.
# La atajada no está en este texto: la hace el motor (simulation._move_ball)
# con los jugadores que tienen is_goalkeeper en True.
PENALTY_GOALKEEPER = """
SPEED_PERCENTAGE = 1.0   # que tan rapido corre, de 0.0 a 1.0 (a ajustar probando)
HALF_GOAL_WIDTH = 3.66   # mitad de GOAL_WIDTH (pitch.py): distancia del centro del arco a cada poste
ARRIVAL_DISTANCE = 0.01  # a esta distancia del poste (en metros) o menos, ya llegue

# Poste hacia el que corro: 1 = el de "y" mayor, -1 = el de "y" menor.
# Vive fuera de on_tick, asi que conserva su valor de un tick al siguiente.
# Cada arquero carga su propia copia de este texto, asi que no lo comparte con otro arquero.
target_post = 1

def post_position(goal_center, post):
    # el poste esta sobre la linea del arco (misma x que el centro), corrido medio arco en y
    return Point2D(goal_center.x, goal_center.y + post * HALF_GOAL_WIDTH)

def on_tick(api):
    global target_post   # para cambiar la variable de afuera, y no crear una nueva dentro de on_tick
    gs = api.get_game_state()

    # si ya llegue al poste al que iba, me doy vuelta: ahora voy hacia el otro
    if gs.my_position.distance_to(post_position(gs.team_goal, target_post)) <= ARRIVAL_DISTANCE:
        target_post = -target_post

    api.run_to(post_position(gs.team_goal, target_post), SPEED_PERCENTAGE)
"""


def assign_penalty_goalkeeper(player: MatchPlayerState) -> None:
    """
    Convierte al jugador en arquero de penales: le asigna PENALTY_GOALKEEPER y
    lo marca con is_goalkeeper, para que el motor le haga atajar la pelota.

    behavior_id queda en None porque este comportamiento no está en la base.
    Si assign_behavior falla, lanza el error y el jugador queda como estaba.
    """
    assign_behavior(player, None, PENALTY_GOALKEEPER)
    player.is_goalkeeper = True
