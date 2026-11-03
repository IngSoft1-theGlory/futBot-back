"""
Comportamientos del sistema para los penales

No se guardan en la base ni aparecen en GET /behaviors: se asignan a mano
a los jugadores con behavior_id None
"""

from src.engine._02_to_match.state import MatchPlayerState
from src.engine._03_to_builder.behavior_executor import assign_behavior

PENALTY_KICKER = """
CORNER_OFFSET = 3.0     # metros desde el centro del arco hacia cada rincon (los postes estan a 3.66)

def on_tick(api):
    gs = api.get_game_state()

    # no patear si la pelota todavia se esta moviendo
    if gs.ball_velocity.magnitude() > 0.1:  # si la pelota va mas despacio que esto, la consideramos quieta
        api.idle()
        return

    # distancia entre el jugador y la pelota
    ball_to_player = gs.ball_position.distance_to(gs.my_position)

    # solo patea si la pelota esta a su alcance
    if ball_to_player <= api.get_reach_distance():
        # lugar del arco elegido al azar: rincon izquierdo, centro o rincon derecho
        offset = random.choice([-CORNER_OFFSET, 0, CORNER_OFFSET])

        # hacia donde patear, de la pelota al arco rival, con un offset para no ir siempre al mismo lugar
        target = Point2D(
            gs.opponent_goal.x,
            gs.opponent_goal.y + offset
        )

        # la direccion de la patada es el vector unitario desde la pelota hasta el target
        direction = gs.ball_position.direction_to(target)
        api.kick_ball(direction, 1.0)
    else: # si no, me quedo quieto
        api.idle()
"""


def assign_penalty_kicker(player: MatchPlayerState) -> None:
    """Le asigna el comportamiento de pateador a player """
    # si el codigo falla, el jugador queda como estaba
    assign_behavior(player, None, PENALTY_KICKER)
    # un jugador puede cambiar de rol entre tandas
    player.is_goalkeeper = False  