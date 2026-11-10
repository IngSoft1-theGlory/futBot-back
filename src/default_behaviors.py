"""
Comportamientos predeterminados del sistema (is_default=True).

Cada uno se guarda en la tabla behaviors como texto (columna `code`).
seed_default_behaviors, en seed.py, los carga en la base.
"""

NEUTRAL = """
def on_tick(api):
    gs = api.get_game_state()

    # distancia entre la pelota y yo
    ball_to_player = gs.ball_position.distance_to(gs.my_position)

    # hacia donde patear: de la pelota al arco rival
    kick_direction = gs.ball_position.direction_to(gs.opponent_goal)

    if ball_to_player <= api.get_reach_distance():
        # si la pelota esta a mi alcance, la pateo a toda potencia
        api.kick_ball(kick_direction, 1.0)
    else:
        # si no, me quedo quieto
        api.idle()
"""

OFENSIVE = """
def on_tick(api):
    gs = api.get_game_state()

    # distancia entre la pelota y yo
    ball_to_player = gs.ball_position.distance_to(gs.my_position)

    # hacia donde patear: de la pelota al arco rival
    kick_direction = gs.ball_position.direction_to(gs.opponent_goal)

    if ball_to_player <= api.get_reach_distance():
        # si la pelota esta a mi alcance, la pateo a toda potencia
        api.kick_ball(kick_direction, 1.0)
    else:
        # si no, corro hacia la pelota a toda velocidad
        api.run_to(gs.ball_position, 1.0)
"""

DEFENSIVE = """
GUARD_DISTANCE = 15   # a cuantos metros de mi arco me paro
DANGER_ZONE = 30      # si la pelota esta mas cerca que esto de mi arco, salgo a buscarla

def on_tick(api):
    gs = api.get_game_state()

    # distancia entre la pelota y mi arco
    ball_to_goal = gs.ball_position.distance_to(gs.team_goal)

    # distancia entre la pelota y yo
    ball_to_player = gs.ball_position.distance_to(gs.my_position)

    # hacia donde patear: de la pelota al arco rival
    kick_direction = gs.ball_position.direction_to(gs.opponent_goal)

    if ball_to_player <= api.get_reach_distance():
        # si la pelota esta a mi alcance, la despejo a toda potencia
        api.kick_ball(kick_direction, 1.0)
        
    elif ball_to_goal < DANGER_ZONE:
        # si la pelota esta cerca de mi arco, salgo a buscarla a toda velocidad
        api.run_to(gs.ball_position, 1.0)
        
    else:
        # si la pelota esta lejos, vuelvo a mi punto de guardia
        # sentido: +1 si ataco hacia la derecha (x creciente), -1 si ataco hacia la izquierda
        if gs.opponent_goal.x > gs.team_goal.x:
            sentido = 1
        else:
            sentido = -1

        # mi punto de guardia: GUARD_DISTANCE metros adelante de mi arco, a su misma altura
        home = Point2D(gs.team_goal.x + (sentido * GUARD_DISTANCE), gs.team_goal.y)
        api.run_to(home, 0.6)
"""

DEFAULT_BEHAVIORS = [
    {
        "name": "Neutro",
        "description": "Se queda quieto y solo patea si la pelota está a su alcance.",
        "code": NEUTRAL,
    },
    {
        "name": "Ofensivo",
        "description": "Corre siempre hacia la pelota y la patea hacia el arco rival.",
        "code": OFENSIVE,
    },
    {
        "name": "Defensor",
        "description": "Se mantiene cerca de su arco y sale a buscar la pelota si se acerca.",
        "code": DEFENSIVE,
    },
]