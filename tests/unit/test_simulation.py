"""
Tests de apply_intentions: aplica las intenciones de todos los jugadores al
MatchState global (posiciones, velocidad de la pelota y reinicio tras un gol).

Se trabaja con un MatchState armado con build_initial_state, sin base de datos.
"""

import pytest

from src.engine._01_to_world.metrics import (
    MAX_ATTRIBUTE_VALUE,
    MAX_KICK_SPEED_METERS_PER_SECOND,
    MAX_RUN_SPEED_METERS_PER_SECOND,
    TICK_DURATION_SECONDS,
    reach_distance,
)
from src.engine._01_to_world.data_types import (
    Point2D, Vector2D, AttributeType, ActionType, Intention
)
from src.engine.match_runner import run_tick
from src.engine._03_to_builder.player_api import PlayerAPI
from src.engine._01_to_world.pitch import BALL_INITIAL_POSITION, TeamSide, detect_goal
from src.engine._04_to_physics.simulation import apply_intentions
from src.engine._02_to_match.state import TeamMatchSetup, build_initial_state
from src.engine._03_to_builder.snapshot import build_player_snapshot
from src.schemas.lineup_config import LineupConfig, StartingPlayer, SubstitutePlayer

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
    lineup = LineupConfig(
        formation_type="2-1",
        starting_players=[
            StartingPlayer(player_id=base_player_id + i, role=role, behavior_id=1)
            for i, role in enumerate(roles)
        ],
        substitute_players=[
            SubstitutePlayer(player_id=base_player_id + 3 + i, behavior_id=1)
            for i in range(3)
        ],
    )
    # los 6 jugadores del equipo con los mismos atributos (los de ATTRIBUTES)
    attributes = {base_player_id + i: dict(ATTRIBUTES) for i in range(6)}
    return TeamMatchSetup(team_id=team_id, side=side, lineup=lineup, attributes=attributes)


def _state():
    """Estado inicial; todos los jugadores con los atributos de ATTRIBUTES."""
    return build_initial_state(
        1,
        240,
        _setup(1, TeamSide.HOME, 100),
        _setup(2, TeamSide.AWAY, 200),
    )


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


@pytest.mark.parametrize(
    "inicio, velocidad, lado_que_convierte, linea_x",
    [
        # Tiros a 30 m/s (15 m por tick) que cruzan el arco entre los palos pero, por la desviación en y,
        # terminarían el tick por afuera de los palos (y=34.05 > 33.66)
        (Point2D(10.7, 30.0), Vector2D(-28.9, 8.1), TeamSide.AWAY, 0.0),
        (Point2D(94.3, 30.0), Vector2D(28.9, 8.1), TeamSide.HOME, 105.0),
    ],
)
def test_deberia_pelota_que_cruza_el_arco_en_un_tick_quedar_quieta_en_la_linea_y_contar_gol(
    inicio, velocidad, lado_que_convierte, linea_x
):
    state = _state()
    state.ball.position = inicio
    state.ball.velocity = velocidad

    apply_intentions(state, {})

    assert state.ball.position.x == pytest.approx(linea_x)
    assert state.ball.velocity == Vector2D(0.0, 0.0)
    assert detect_goal(state.ball.position) == lado_que_convierte

# REBOTE DE LA PELOTA EN LOS LÍMITES DE LA CANCHA

def _tick_con_la_pelota_en(posicion: Point2D, velocidad: Vector2D):
    # Preparamos un estado de partido limpio desde cero
    state = _state()
    
    state.ball.position = posicion
    state.ball.velocity = velocidad
    
    apply_intentions(state, {})
    
    return state


@pytest.mark.parametrize(
    "inicio, velocidad, posicion_final, velocidad_final",
    [
        # Lateral superior e inferior: la pelota choca la banda y rebota invirtiendo solo el eje Y
        # El límite inferior en y=0.0 y el superior en y=60.0 (la cancha mide 60 m de alto)
        # Por ello se prueban los bordes 58.0 y 2.0, con velocidades de 6 m/s hacia arriba y hacia 
        # abajo respectivamente
        (Point2D(50.0, 58.0), Vector2D(0.0, 6.0), Point2D(50.0, 59.0), Vector2D(0.0, -6.0)),
        (Point2D(50.0, 2.0), Vector2D(0.0, -6.0), Point2D(50.0, 1.0), Vector2D(0.0, 6.0)),
        
        # Línea de fondo fuera del arco: choca la pared del fondo y rebota invirtiendo solo el eje X
        # El límite izquierdo en x=0.0 y el derecho en x=105.0 (la cancha mide 105 m de ancho)
        # Por ello se prueban los bordes 3.0 y 102.0, con velocidades de 8 m/s hacia la izquierda 
        # y hacia la derecha respectivamente.
        (Point2D(3.0, 10.0), Vector2D(-8.0, 0.0), Point2D(1.0, 10.0), Vector2D(8.0, 0.0)),
        (Point2D(102.0, 10.0), Vector2D(8.0, 0.0), Point2D(104.0, 10.0), Vector2D(-8.0, 0.0)),
        
        # Esquina: pega justo en el vértice de la cancha y rebota en diagonal 
        # invirtiendo ambos ejes (X e Y)
        (Point2D(103.0, 58.0), Vector2D(10.0, 10.0), Point2D(102.0, 57.0), Vector2D(-10.0, -10.0)),
    ],
)
def test_deberia_pelota_que_sale_de_la_cancha_rebotar_en_la_direccion_opuesta(
    inicio, velocidad, posicion_final, velocidad_final
):
    # Hacemos correr la pelota hacia el borde según el escenario configurado
    state = _tick_con_la_pelota_en(inicio, velocidad)

    # Verificamos que la posición resultante tras el impacto coincida con la coordenada esperada
    assert state.ball.position.x == pytest.approx(posicion_final.x)
    assert state.ball.position.y == pytest.approx(posicion_final.y)
    
    # Confirmamos que la velocidad invirtió su sentido en los ejes correspondientes
    assert state.ball.velocity.x == pytest.approx(velocidad_final.x)
    assert state.ball.velocity.y == pytest.approx(velocidad_final.y)


def test_deberia_pelota_que_rebota_conservar_la_rapidez():
    # Le imprimimos a la pelota una velocidad diagonal con decimales específicos (-7.3, -11.9)
    velocidad = Vector2D(-7.3, -11.9)

    # La colocamos a pasos de la esquina (2.0, 1.0) para que en este tick choque contra 
    # el vértice de la cancha.
    state = _tick_con_la_pelota_en(Point2D(2.0, 1.0), velocidad)

    # La rapidez debe mantenerse totalmente intacta tras el choque
    assert state.ball.velocity.magnitude() == pytest.approx(velocidad.magnitude())
    
    # En el eje X cruzó la línea de fondo, por lo que invierte su velocidad a positiva
    assert state.ball.velocity.x == pytest.approx(7.3)
    
    # En el eje Y cruzó la banda lateral, por lo que invierte su velocidad a positiva
    assert state.ball.velocity.y == pytest.approx(11.9)


@pytest.mark.parametrize(
    "inicio, velocidad, lado_que_convierte, linea_x",
    [
        # Pelota dirigida directo al arco local (x=0)
        (Point2D(3.0, 30.0), Vector2D(-8.0, 0.0), TeamSide.AWAY, 0.0),
        # Pelota dirigida directo al arco visitante (x=105)
        (Point2D(102.0, 30.0), Vector2D(8.0, 0.0), TeamSide.HOME, 105.0),
    ],
)
def test_deberia_pelota_que_entra_al_arco_no_rebotar(inicio, velocidad, lado_que_convierte, linea_x):
    # Lanzamos la pelota hacia el arco durante el tick actual
    state = _tick_con_la_pelota_en(inicio, velocidad)

    # Al ser gol entre los postes, el balón no debe rebotar: se frena en seco sobre la línea de meta
    assert state.ball.position.x == pytest.approx(linea_x)
    assert state.ball.velocity == Vector2D(0.0, 0.0)
    
    # El detector convalida el tanto para el equipo atacante
    assert detect_goal(state.ball.position) == lado_que_convierte


def _behavior_quieto(_state, _player_id):
    # Comportamiento auxiliar donde los jugadores deciden quedarse totalmente inactivos
    return Intention(ActionType.IDLE)


@pytest.mark.parametrize("y_del_tiro", [20.0, 25.0])  # y=25.0 pasa pegado afuera del palo
def test_deberia_tiro_desviado_rebotar_y_no_contar_gol(y_del_tiro):
    # Preparamos la jugada: tiro rasante al fondo pero desviado por fuera de los tres palos
    state = _state()
    state.ball.position = Point2D(3.0, y_del_tiro)
    state.ball.velocity = Vector2D(-8.0, 0.0)

    # Avanzamos el tick completo del partido con los jugadores inmóviles
    run_tick(state, execute_behavior=_behavior_quieto, apply_intentions=apply_intentions, detect_goal=detect_goal)

    # Al no pasar entre los postes, el marcador se mantiene intacto en cero a cero
    assert (state.score.home, state.score.away) == (0, 0)
    
    # La pelota choca contra la pared de fondo fuera del arco y rebota hacia adentro del campo de juego
    assert state.ball.position.x == pytest.approx(1.0)
    assert state.ball.velocity.x == pytest.approx(8.0)

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
        Point2D(100.0, 30.0),  # cerca del arco, pero su recorrido de este tick no llega a la línea
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
    Pelota en el arco; el jugador arranca el partido junto al centro: tras el
    reinicio la pelota queda a su alcance y la patada del mismo tick se aplica.
    """
    state = _state()
    state.ball.position = Point2D(0.0, 30.0)
    state.players[FORWARD_HOME].initial_position = Point2D(BALL_INITIAL_POSITION.x - 1.0, BALL_INITIAL_POSITION.y)

    apply_intentions(state, {FORWARD_HOME: _kick(Vector2D(1, 0))})

    # reiniciada al centro y luego pateada: avanza desde el centro, no desde el arco
    assert state.ball.position.x == pytest.approx(BALL_INITIAL_POSITION.x + MAX_KICK_SPEED * TICK_DURATION_SECONDS)
    assert state.ball.velocity.x == pytest.approx(MAX_KICK_SPEED)


def _state_con_los_jugadores_lejos_de_su_posicion_inicial():
    """Devuelve (state, posiciones iniciales) con los 6 titulares movidos a otro lado."""
    state = _state()
    iniciales = {pid: p.position for pid, p in state.players.items() if p.position is not None}
    for jugador in state.players.values():
        if jugador.position is not None:
            jugador.position = Point2D(jugador.position.x + 7.0, jugador.position.y - 3.0)
    return state, iniciales


def test_deberia_devolver_a_todos_los_jugadores_en_cancha_a_su_posicion_inicial_tras_un_gol():
    state, iniciales = _state_con_los_jugadores_lejos_de_su_posicion_inicial()
    state.ball.position = Point2D(0.0, 30.0)  # gol del tick anterior

    apply_intentions(state, {})

    assert {pid: p.position for pid, p in state.players.items() if p.position is not None} == iniciales
    assert len(iniciales) == 6  # los dos equipos

def test_deberia_no_reubicar_a_un_jugador_fuera_de_cancha_aunque_tenga_posicion_inicial():
    """Un titular que salió del campo (position=None) no reaparece en cancha tras un gol."""
    state = _state()
    state.players[FORWARD_HOME].position = None  # fuera de cancha, pero con su initial_position cargada
    state.ball.position = Point2D(0.0, 30.0)

    apply_intentions(state, {})

    assert state.players[FORWARD_HOME].position is None


def test_deberia_el_jugador_correr_desde_su_posicion_inicial_en_el_tick_del_reinicio():
    """La carrera del tick del reinicio parte de donde quedó el jugador tras volver, no de donde estaba."""
    state, iniciales = _state_con_los_jugadores_lejos_de_su_posicion_inicial()
    state.ball.position = Point2D(0.0, 30.0)
    inicial = iniciales[FORWARD_HOME]
    destino = Point2D(inicial.x + 10.0, inicial.y)

    apply_intentions(state, {FORWARD_HOME: _run_to(destino)})

    paso = state.players[FORWARD_HOME].position.distance_to(inicial)
    assert 0.0 < paso <= MAX_RUN_SPEED_METERS_PER_SECOND * TICK_DURATION_SECONDS + 1e-9

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
