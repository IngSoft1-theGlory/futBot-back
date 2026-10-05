"""
Tests de apply_intentions: aplica las intenciones de todos los jugadores al
MatchState global (posiciones, velocidad de la pelota y reinicio tras un gol).

Se trabaja con un MatchState armado con build_initial_state, sin base de datos.
"""

import pytest

from src.engine.constants import MAX_ATTRIBUTE_VALUE, MAX_KICK_SPEED_METERS_PER_SECOND, reach_distance
from src.engine.game_types import AttributeType
from src.engine.geometry_types import Point2D, Vector2D
from src.engine.intentions import ActionType, Intention
from src.engine.match_runner import run_tick
from src.engine.pitch import BALL_INITIAL_POSITION, TeamSide, detect_goal
from src.engine.player_api import PlayerAPI
from src.engine.simulation import apply_intentions
from src.engine.snapshot import build_player_snapshot
from src.engine.state import LineupPlayer, TeamMatchSetup, build_initial_state
from src.engine.timing import TICK_DURATION_SECONDS

# Todos distintos, para detectar cruces entre atributos.
ATTRIBUTES = {
    AttributeType.POWER: 20,
    AttributeType.AGILITY: 30,
    AttributeType.CONTROL: 40,
    AttributeType.SPEED: 50,
    AttributeType.STRENGTH: 60,
}
MAX_KICK_SPEED = MAX_KICK_SPEED_METERS_PER_SECOND * ATTRIBUTES[AttributeType.POWER] / MAX_ATTRIBUTE_VALUE  # 6 m/s
REACH = reach_distance(ATTRIBUTES[AttributeType.CONTROL])  # 1.625 m

# Titulares con la formación "2-1" (ver pitch.FORMATION_POSITIONS):
#   HOME: 100 DEF_LEFT (25,45) | 101 DEF_RIGHT (25,15) | 102 FORWARD (70,30)
#   AWAY: 200 DEF_LEFT (80,15) | 201 DEF_RIGHT (80,45) | 202 FORWARD (35,30)
# Suplentes: 103-105 (HOME) y 203-205 (AWAY), sin posición (en el banco).
FORWARD_HOME = 102
FORWARD_AWAY = 202
SUBSTITUTE_HOME = 103


def _setup(team_id: int, side: TeamSide, base_player_id: int) -> TeamMatchSetup:
    roles = ["DEF_LEFT", "DEF_RIGHT", "FORWARD"]
    starters = [
        LineupPlayer(player_id=base_player_id + i, is_starter=True, role=role, behavior_id=1)
        for i, role in enumerate(roles)
    ]
    substitutes = [
        LineupPlayer(player_id=base_player_id + 3 + i, is_starter=False, role=None, behavior_id=1)
        for i in range(3)
    ]
    return TeamMatchSetup(team_id=team_id, formation_type="2-1", side=side, players=starters + substitutes)


def _state():
    """Estado inicial con atributos cargados a mano (build_initial_state todavía no los carga)."""
    state = build_initial_state(
        1,
        240,
        _setup(1, TeamSide.HOME, 100),
        _setup(2, TeamSide.AWAY, 200),
    )
    for player in state.players.values():
        player.attributes = dict(ATTRIBUTES)
    return state


def _state_con_pelota_junto_al(player_id: int, distancia: float):
    """Pelota en reposo a `distancia` metros (eje x) del jugador `player_id`."""
    state = _state()
    jugador = state.players[player_id].position
    state.ball.position = Point2D(jugador.x + distancia, jugador.y)
    state.ball.velocity = Vector2D(0.0, 0.0)
    return state


def _kick(direction: Vector2D, power_percentage: float = 1.0) -> Intention:
    return Intention(ActionType.KICK_BALL, direction=direction, power_percentage=power_percentage)


def _run_to(target: Point2D, speed_percentage: float = 1.0) -> Intention:
    return Intention(ActionType.RUN_TO, target=target, speed_percentage=speed_percentage)


# --- IDLE ---

def test_deberia_idle_no_cambiar_posiciones_ni_pelota():
    state = _state()
    posiciones = {pid: p.position for pid, p in state.players.items()}
    pelota = (state.ball.position, state.ball.velocity)  # en reposo

    apply_intentions(state, {pid: Intention(ActionType.IDLE) for pid in state.on_pitch_player_ids()})

    assert {pid: p.position for pid, p in state.players.items()} == posiciones
    assert (state.ball.position, state.ball.velocity) == pelota


def test_deberia_sin_intenciones_no_cambiar_nada():
    state = _state()
    pelota = (state.ball.position, state.ball.velocity)

    apply_intentions(state, {})

    assert (state.ball.position, state.ball.velocity) == pelota


# --- RUN_TO ---

def test_deberia_run_to_mover_al_jugador_en_el_estado_global():
    state = _state()
    inicio = state.players[FORWARD_HOME].position

    apply_intentions(state, {FORWARD_HOME: _run_to(Point2D(100, 30))})

    # SPEED 50 a fondo: 4 m/s * 0.5 s = 2 m por tick, hacia +x
    assert state.players[FORWARD_HOME].position.x == pytest.approx(inicio.x + 2.0)
    assert state.players[FORWARD_HOME].position.y == pytest.approx(inicio.y)


def test_deberia_run_to_mover_solo_al_jugador_que_corre():
    state = _state()
    otros = {pid: p.position for pid, p in state.players.items() if pid != FORWARD_HOME}

    apply_intentions(state, {FORWARD_HOME: _run_to(Point2D(100, 30))})

    assert {pid: p.position for pid, p in state.players.items() if pid != FORWARD_HOME} == otros


def test_deberia_run_to_no_cambiar_la_velocidad_de_la_pelota():
    state = _state()
    state.ball.velocity = Vector2D(2.0, 3.0)

    apply_intentions(state, {FORWARD_HOME: _run_to(Point2D(100, 30))})

    assert state.ball.velocity == Vector2D(2.0, 3.0)  # correr no cambia la velocidad de la pelota


def test_deberia_varios_run_to_en_el_mismo_tick_moverse_todos():
    state = _state()
    inicio_home = state.players[FORWARD_HOME].position
    inicio_away = state.players[FORWARD_AWAY].position

    apply_intentions(
        state,
        {FORWARD_HOME: _run_to(Point2D(100, 30)), FORWARD_AWAY: _run_to(Point2D(0, 30))},
    )

    assert state.players[FORWARD_HOME].position.x > inicio_home.x
    assert state.players[FORWARD_AWAY].position.x < inicio_away.x


# --- KICK_BALL ---

def test_deberia_kick_ball_en_alcance_cambiar_la_velocidad_de_la_pelota():
    state = _state_con_pelota_junto_al(FORWARD_HOME, 1.0)

    apply_intentions(state, {FORWARD_HOME: _kick(Vector2D(0, 1))})

    assert state.ball.velocity.x == pytest.approx(0.0)
    assert state.ball.velocity.y == pytest.approx(MAX_KICK_SPEED)


def test_deberia_kick_ball_mover_la_pelota_en_el_mismo_tick():
    state = _state_con_pelota_junto_al(FORWARD_HOME, 1.0)
    antes = state.ball.position

    apply_intentions(state, {FORWARD_HOME: _kick(Vector2D(1, 0))})

    assert state.ball.position.x == pytest.approx(antes.x + MAX_KICK_SPEED * TICK_DURATION_SECONDS)
    assert state.ball.position.y == pytest.approx(antes.y)


def test_deberia_kick_ball_no_mover_al_jugador_que_patea():
    state = _state_con_pelota_junto_al(FORWARD_HOME, 1.0)
    antes = state.players[FORWARD_HOME].position

    apply_intentions(state, {FORWARD_HOME: _kick(Vector2D(1, 0))})

    assert state.players[FORWARD_HOME].position == antes


def test_deberia_kick_ball_fuera_de_alcance_dejar_la_pelota_sin_cambios():
    state = _state_con_pelota_junto_al(FORWARD_HOME, REACH + 0.01)
    state.ball.velocity = Vector2D(1.0, 2.0)

    apply_intentions(state, {FORWARD_HOME: _kick(Vector2D(1, 0))})

    assert state.ball.velocity == Vector2D(1.0, 2.0)


def test_deberia_kick_ball_justo_en_el_borde_del_alcance_patear():
    state = _state_con_pelota_junto_al(FORWARD_HOME, REACH)

    apply_intentions(state, {FORWARD_HOME: _kick(Vector2D(1, 0))})

    assert state.ball.velocity.x == pytest.approx(MAX_KICK_SPEED)


def test_deberia_kick_ball_con_power_percentage_cero_dejar_la_pelota_sin_velocidad():
    state = _state_con_pelota_junto_al(FORWARD_HOME, 1.0)
    state.ball.velocity = Vector2D(3.0, 4.0)

    apply_intentions(state, {FORWARD_HOME: _kick(Vector2D(1, 0), 0.0)})

    assert state.ball.velocity.magnitude() == pytest.approx(0.0)


def test_deberia_kick_ball_con_la_pelota_lejos_de_todos_no_hacer_nada():
    """Pelota en el centro: ningún jugador inicial está a su alcance."""
    state = _state()

    apply_intentions(state, {pid: _kick(Vector2D(1, 0)) for pid in state.on_pitch_player_ids()})

    assert state.ball.velocity == Vector2D(0.0, 0.0)


def test_deberia_kick_ball_medir_el_alcance_con_el_control_de_quien_patea():
    """A 3 m: el jugador con CONTROL 100 (5 m) llega, el de CONTROL 40 (1.6 m) no."""
    state = _state_con_pelota_junto_al(FORWARD_HOME, 3.0)
    state.players[FORWARD_HOME].attributes[AttributeType.CONTROL] = 100

    apply_intentions(state, {FORWARD_HOME: _kick(Vector2D(1, 0))})
    con_control_alto = state.ball.velocity

    state = _state_con_pelota_junto_al(FORWARD_HOME, 3.0)
    apply_intentions(state, {FORWARD_HOME: _kick(Vector2D(1, 0))})
    con_control_normal = state.ball.velocity

    assert con_control_alto.magnitude() > 0
    assert con_control_normal.magnitude() == 0


def test_deberia_kick_ball_de_un_rival_tambien_mover_la_pelota():
    """Quien patea puede ser de cualquier equipo."""
    state = _state_con_pelota_junto_al(FORWARD_AWAY, 1.0)

    apply_intentions(state, {FORWARD_AWAY: _kick(Vector2D(-1, 0))})

    assert state.ball.velocity.x == pytest.approx(-MAX_KICK_SPEED)


# --- Dos jugadores en el mismo tick (política PROVISORIA: gana el player_id más alto) ---

def _state_con_dos_a_alcance():
    """Pelota en reposo con el 102 (HOME) y el 202 (AWAY) los dos a 1 m de ella."""
    state = _state_con_pelota_junto_al(FORWARD_HOME, 1.0)
    state.players[FORWARD_AWAY].position = Point2D(state.ball.position.x, state.ball.position.y + 1.0)
    return state


def test_deberia_dos_patadas_en_el_mismo_tick_ganar_el_player_id_mas_alto():
    state = _state_con_dos_a_alcance()

    apply_intentions(state, {FORWARD_HOME: _kick(Vector2D(1, 0)), FORWARD_AWAY: _kick(Vector2D(-1, 0))})

    assert state.ball.velocity.x == pytest.approx(-MAX_KICK_SPEED)


def test_deberia_resultado_de_dos_patadas_no_depender_del_orden_del_diccionario():
    a = _state_con_dos_a_alcance()
    b = _state_con_dos_a_alcance()

    apply_intentions(a, {FORWARD_HOME: _kick(Vector2D(1, 0)), FORWARD_AWAY: _kick(Vector2D(-1, 0))})
    apply_intentions(b, {FORWARD_AWAY: _kick(Vector2D(-1, 0)), FORWARD_HOME: _kick(Vector2D(1, 0))})

    assert a.ball.velocity == b.ball.velocity


def test_deberia_patada_fuera_de_alcance_no_pisar_la_patada_de_otro():
    """El 202 (más alto) está lejos: su patada fallida no borra la del 102."""
    state = _state_con_pelota_junto_al(FORWARD_HOME, 1.0)

    apply_intentions(state, {FORWARD_HOME: _kick(Vector2D(1, 0)), FORWARD_AWAY: _kick(Vector2D(-1, 0))})

    assert state.ball.velocity.x == pytest.approx(MAX_KICK_SPEED)


def test_deberia_correr_y_patear_en_el_mismo_tick_aplicar_las_dos_cosas():
    state = _state_con_pelota_junto_al(FORWARD_HOME, 1.0)
    inicio_rival = state.players[FORWARD_AWAY].position

    apply_intentions(state, {FORWARD_HOME: _kick(Vector2D(1, 0)), FORWARD_AWAY: _run_to(Point2D(0, 30))})

    assert state.ball.velocity.x == pytest.approx(MAX_KICK_SPEED)
    assert state.players[FORWARD_AWAY].position.x < inicio_rival.x


# --- Movimiento de la pelota ---

def test_deberia_pelota_en_movimiento_avanzar_velocidad_por_duracion_del_tick():
    state = _state()
    state.ball.velocity = Vector2D(4.0, -2.0)

    apply_intentions(state, {})

    assert state.ball.position.x == pytest.approx(BALL_INITIAL_POSITION.x + 4.0 * TICK_DURATION_SECONDS)
    assert state.ball.position.y == pytest.approx(BALL_INITIAL_POSITION.y - 2.0 * TICK_DURATION_SECONDS)


def test_deberia_pelota_quieta_quedarse_donde_esta():
    state = _state()

    apply_intentions(state, {})

    assert state.ball.position == BALL_INITIAL_POSITION


def test_deberia_pelota_patada_hacia_el_arco_terminar_dentro_y_run_tick_contar_el_gol():
    """Patada desde cerca del arco AWAY: en el mismo tick entra y se cuenta el gol."""
    state = _state()
    state.ball.position = Point2D(104.0, 30.0)
    state.players[FORWARD_HOME].position = Point2D(103.5, 30.0)
    # el arco está a 1 m: con 6 m/s * 0.5 s = 3 m la pelota cruza la línea de fondo

    run_tick(
        state,
        execute_behavior=_behavior_que_patea(Vector2D(1, 0), 1.0),
        apply_intentions=apply_intentions,
        detect_goal=detect_goal,
    )

    assert state.score.home == 1


# --- Reinicio de la pelota tras un gol ---

@pytest.mark.parametrize(
    "posicion",
    [
        Point2D(0.0, 30.0),    # dentro del arco de HOME
        Point2D(-1.0, 30.0),   # pasó la línea de fondo de HOME
        Point2D(105.0, 30.0),  # dentro del arco de AWAY
        Point2D(106.0, 28.0),  # pasó la línea de fondo de AWAY
    ],
)
def test_deberia_pelota_en_un_arco_volver_al_centro_y_quedar_quieta(posicion):
    state = _state()
    state.ball.position = posicion
    state.ball.velocity = Vector2D(5.0, 5.0)

    apply_intentions(state, {})

    assert state.ball.position == BALL_INITIAL_POSITION
    assert state.ball.velocity == Vector2D(0.0, 0.0)


@pytest.mark.parametrize(
    "posicion",
    [
        Point2D(0.0, 5.0),    # línea de fondo pero afuera del arco (no es gol)
        Point2D(50.0, 30.0),
        Point2D(104.0, 30.0),
    ],
)
def test_deberia_pelota_fuera_de_un_arco_no_reiniciarse(posicion):
    state = _state()
    state.ball.position = posicion
    state.ball.velocity = Vector2D(5.0, 5.0)

    apply_intentions(state, {})

    assert state.ball.velocity == Vector2D(5.0, 5.0)
    # no hubo reinicio: la pelota siguió su camino desde donde estaba
    assert state.ball.position.x == pytest.approx(posicion.x + 5.0 * TICK_DURATION_SECONDS)
    assert state.ball.position.y == pytest.approx(posicion.y + 5.0 * TICK_DURATION_SECONDS)


def test_deberia_reiniciar_la_pelota_antes_de_resolver_las_patadas():
    """
    Pelota en el arco + jugador parado junto al centro: tras el reinicio la
    pelota queda a su alcance y la patada del mismo tick se aplica.
    """
    state = _state()
    state.ball.position = Point2D(0.0, 30.0)
    state.players[FORWARD_HOME].position = Point2D(BALL_INITIAL_POSITION.x - 1.0, BALL_INITIAL_POSITION.y)

    apply_intentions(state, {FORWARD_HOME: _kick(Vector2D(1, 0))})

    # reiniciada al centro y luego pateada: avanza desde el centro, no desde el arco
    assert state.ball.position.x == pytest.approx(BALL_INITIAL_POSITION.x + MAX_KICK_SPEED * TICK_DURATION_SECONDS)
    assert state.ball.velocity.x == pytest.approx(MAX_KICK_SPEED)


def test_deberia_no_mover_a_los_jugadores_al_reiniciar_la_pelota():
    state = _state()
    posiciones = {pid: p.position for pid, p in state.players.items()}
    state.ball.position = Point2D(0.0, 30.0)

    apply_intentions(state, {})

    assert {pid: p.position for pid, p in state.players.items()} == posiciones


# --- Jugadores en el banco ---

def test_deberia_ignorar_la_intencion_de_un_suplente():
    state = _state()

    apply_intentions(state, {SUBSTITUTE_HOME: _run_to(Point2D(50, 30))})

    assert state.players[SUBSTITUTE_HOME].position is None


# --- Integración con run_tick y PlayerAPI ---

def _no_goal(state):
    return None


def _behavior_que_patea(direction, power_percentage):
    """execute_behavior de juguete: arma el PlayerAPI como lo haría el motor y llama a kick_ball."""

    def execute(state, player_id):
        game_state, attributes = build_player_snapshot(state, player_id)
        api = PlayerAPI(game_state, attributes)
        api.kick_ball(direction, power_percentage)
        return api.intention

    return execute


def test_deberia_run_tick_con_kick_ball_real_cambiar_la_velocidad_y_avanzar_el_tick():
    state = _state_con_pelota_junto_al(FORWARD_HOME, 1.0)

    run_tick(
        state,
        execute_behavior=_behavior_que_patea(Vector2D(1, 0), 1.0),
        apply_intentions=apply_intentions,
        detect_goal=_no_goal,
    )

    assert state.ball.velocity.x == pytest.approx(MAX_KICK_SPEED)
    assert state.players[FORWARD_HOME].current_action == ActionType.KICK_BALL
    assert state.current_tick == 1


def test_deberia_kick_ball_invalido_no_interrumpir_el_ciclo_del_partido():
    """power_percentage fuera de rango: ValueError -> run_tick le da IDLE y el tick se completa."""
    state = _state_con_pelota_junto_al(FORWARD_HOME, 1.0)

    run_tick(
        state,
        execute_behavior=_behavior_que_patea(Vector2D(1, 0), 5.0),
        apply_intentions=apply_intentions,
        detect_goal=_no_goal,
    )

    assert state.ball.velocity == Vector2D(0.0, 0.0)
    assert state.players[FORWARD_HOME].current_action == ActionType.IDLE
    assert state.current_tick == 1
