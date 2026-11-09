"""
Tests de los comportamientos del sistema para los penales (penalty_behaviors.py).

tests
  CA1  assign_penalty_kicker deja behavior_id None, is_goalkeeper False y un on_tick ejecutable
  CA2  pelota quieta y a su alcance: patea a potencia 1.0 hacia un punto entre los postes
  CA3  pelota fuera de su alcance o ya en movimiento: idle
"""

from src.engine._01_to_world.data_types import ActionType, AttributeType, Point2D, Vector2D
from src.engine._01_to_world.pitch import HOME_GOAL, TeamSide
from src.engine._02_to_match.state import BallState, MatchPhase, MatchPlayerState, MatchState, Score
from src.engine._03_to_builder.behavior_executor import execute_behavior
from src.penalty_behaviors import assign_penalty_kicker


# atributos del pateador de prueba (alcance = 0.05625 * 60 - 0.625 = 2.75 m)
# Sin CONTROL el comportamiento no puede calcular su alcance
ATTRIBUTES = {
    AttributeType.POWER: 80,
    AttributeType.AGILITY: 50,
    AttributeType.CONTROL: 60,
    AttributeType.SPEED: 80,
    AttributeType.STRENGTH: 30,
}

PENALTY_SPOT = Point2D(11, 30)  # donde esta la pelota en el penal


def crear_estado(kicker_position=Point2D(10, 30), ball_velocity=Vector2D(0, 0)):
    """
    Penal de prueba un solo jugador, el pateador, con la pelota en el punto penal,
    Es AWAY, asi que su arco rival es el de x=0 (el mismo que se usa en el penal real),
    Por defecto esta a 1 m de la pelota y la pelota esta quieta, devuelve (estado, pateador)
    """
    pateador = MatchPlayerState(
        player_id=1,
        team_id=1,
        side=TeamSide.AWAY,
        is_starter=True,
        role=None,
        behavior_id=None,
        position=kicker_position,
        attributes=dict(ATTRIBUTES),
    )
    estado = MatchState(
        match_id=1,
        phase=MatchPhase.IN_PROGRESS,
        current_tick=0,
        total_ticks=100,
        score=Score(),
        ball=BallState(position=PENALTY_SPOT, velocity=ball_velocity),
        players={1: pateador},
    )
    return estado, pateador


def y_donde_cruza_la_linea_de_gol(desde: Point2D, direccion: Vector2D) -> float:
    """
    La pelota sale de desde en linea recta hacia direccion, devuelve la y en la que
    cruza la linea de gol (x=0). Es una regla de tres, por cada metro que avanza en x, avanza
    direccion.y / direccion.x en y.
    """
    metros_en_x = HOME_GOAL.line_x - desde.x
    return desde.y + direccion.y * metros_en_x / direccion.x


def test_deberia_asignar_pateador_sin_behavior_id_y_con_on_tick_ejecutable():
    estado, pateador = crear_estado()
    pateador.behavior_id = 5          # venia con un comportamiento de usuario
    pateador.is_goalkeeper = True     # y de arquero en la tanda anterior

    assign_penalty_kicker(pateador)

    assert pateador.behavior_id is None
    assert pateador.is_goalkeeper is False   # un jugador puede cambiar de rol entre tandas
    assert callable(pateador.on_tick)
    # ademas de ser callable, se puede ejecutar: devuelve una intencion sin lanzar error
    assert execute_behavior(estado, 1) is not None


def test_deberia_patear_a_potencia_1_entre_los_postes_con_pelota_quieta_y_a_su_alcance():
    estado, pateador = crear_estado()
    assign_penalty_kicker(pateador)

    # se repite varias veces porque el lugar se elige al azar, tiene que valer para todos
    for _ in range(50):
        intencion = execute_behavior(estado, 1)

        assert intencion.action == ActionType.KICK_BALL
        assert intencion.power_percentage == 1.0

        y = y_donde_cruza_la_linea_de_gol(PENALTY_SPOT, intencion.direction)
        assert HOME_GOAL.post_min_y <= y <= HOME_GOAL.post_max_y


def test_deberia_elegir_distintos_lugares_del_arco():
    estado, pateador = crear_estado()
    assign_penalty_kicker(pateador)

    lugares = set()
    for _ in range(100):
        intencion = execute_behavior(estado, 1)
        lugares.add(round(y_donde_cruza_la_linea_de_gol(PENALTY_SPOT, intencion.direction), 2))

    # son tres lugares fijos (rincon izquierdo, centro y rincon derecho) con 100 intentos
    # es practicamente imposible que salga siempre el mismo
    assert len(lugares) > 1


def test_deberia_quedarse_quieto_si_la_pelota_esta_fuera_de_su_alcance():
    estado, pateador = crear_estado(kicker_position=Point2D(30, 30))  # a 19 m de la pelota
    assign_penalty_kicker(pateador)

    intencion = execute_behavior(estado, 1)

    assert intencion.action == ActionType.IDLE


def test_deberia_quedarse_quieto_si_la_pelota_ya_esta_en_movimiento():
    # el pateador esta a su alcance, pero la pelota ya viene en movimiento (ya la pateo)
    estado, pateador = crear_estado(ball_velocity=Vector2D(-10, 3))
    assign_penalty_kicker(pateador)

    intencion = execute_behavior(estado, 1)

    assert intencion.action == ActionType.IDLE