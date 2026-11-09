"""
Tests de apply_intentions: simulación física y aplicación de intenciones de los jugadores.
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
from src.default_behaviors import OFENSIVE
from src.engine._01_to_world.pitch import BALL_INITIAL_POSITION, KICKOFF_OFFSET, TeamSide, detect_goal
from src.engine._03_to_builder.behavior_executor import assign_behavior, execute_behavior
from src.engine._04_to_physics.simulation import apply_intentions
from src.engine._02_to_match.state import TeamMatchSetup, build_initial_state
from src.engine._03_to_builder.snapshot import build_player_snapshot
from src.schemas.lineup_config import LineupConfig, StartingPlayer, SubstitutePlayer


# CONFIGURACIÓN DEL ESCENARIO
# Seteamos atributos fijos para poder deducir y comprobar los cálculos físicos.
ATTRIBUTES = {
    AttributeType.POWER: 20,      
    AttributeType.AGILITY: 30,    
    AttributeType.CONTROL: 40,    
    AttributeType.SPEED: 50,      
    AttributeType.STRENGTH: 60,   
}

# Velocidad máxima de remate.
MAX_KICK_SPEED = MAX_KICK_SPEED_METERS_PER_SECOND * ATTRIBUTES[AttributeType.POWER] / MAX_ATTRIBUTE_VALUE

# Radio de alcance de interacción con la pelota.
REACH = reach_distance(ATTRIBUTES[AttributeType.CONTROL])


FORWARD_HOME = 102     # Delantero local (inicia en x=70, y=30)
FORWARD_AWAY = 202     # Delantero visitante (inicia en x=35, y=30)
SUBSTITUTE_HOME = 103  # Suplente local (en el banco, sin posición en cancha)

# FUNCIONES AUXILIARES 

def _setup(team_id: int, side: TeamSide, base_player_id: int) -> TeamMatchSetup:
    """Formamos el equipo con 3 titulares en cancha y 3 suplentes en el banco."""
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
    attributes = {base_player_id + i: dict(ATTRIBUTES) for i in range(6)}
    return TeamMatchSetup(team_id=team_id, side=side, lineup=lineup, attributes=attributes)


def _state():
    """Construimos el estado inicial completo del partido entre el equipo HOME y AWAY."""
    return build_initial_state(
        1,
        240,
        _setup(1, TeamSide.HOME, 100),
        _setup(2, TeamSide.AWAY, 200),
    )


def _state_con_pelota_junto_al(player_id: int, distancia: float):
    """Ponemos la pelota detenida a cierta distancia exacta (en el eje X) del jugador indicado."""
    state = _state()
    jugador = state.players[player_id].position
    state.ball.position = Point2D(jugador.x + distancia, jugador.y)
    state.ball.velocity = Vector2D(0.0, 0.0)
    return state


def _kick(direction: Vector2D, power_percentage: float = 1.0) -> Intention:
    """Fabrica una intención de patear con cierta dirección y porcentaje de potencia."""
    return Intention(ActionType.KICK_BALL, direction=direction, power_percentage=power_percentage)


def _run_to(target: Point2D, speed_percentage: float = 1.0) -> Intention:
    """Fabrica una intención de correr hacia un objetivo."""
    return Intention(ActionType.RUN_TO, target=target, speed_percentage=speed_percentage)



# SECCIÓN 1: ACCIÓN IDLE Y SIN INTENCIONES

def test_deberia_idle_no_cambiar_posiciones_ni_pelota():
    # Arrancamos con el estado inicial limpio
    state = _state()
    posiciones_iniciales = {pid: p.position for pid, p in state.players.items()}
    estado_pelota_inicial = (state.ball.position, state.ball.velocity)

    # Todos los titulares deciden no realizar ninguna acción (IDLE)
    apply_intentions(state, {pid: Intention(ActionType.IDLE) for pid in state.on_pitch_player_ids()})

    # Verificamos que absolutamente nada se haya movido en el campo de juego
    assert {pid: p.position for pid, p in state.players.items()} == posiciones_iniciales
    assert (state.ball.position, state.ball.velocity) == estado_pelota_inicial


def test_deberia_sin_intenciones_no_cambiar_nada():
    # Mandamos un diccionario de intenciones totalmente vacío al motor
    state = _state()
    estado_pelota_inicial = (state.ball.position, state.ball.velocity)

    # El motor procesa el tick sin recibir órdenes de los jugadores
    apply_intentions(state, {})

    # La pelota mantiene su estado inmóvil
    assert (state.ball.position, state.ball.velocity) == estado_pelota_inicial



# SECCIÓN 2: ACCIÓN RUN_TO (DESPLAZAMIENTO)

def test_deberia_run_to_mover_al_jugador_en_el_estado_global():
    # El delantero local se ubica en su posición original (70, 30)
    state = _state()
    posicion_inicial = state.players[FORWARD_HOME].position

    # El delantero decide correr a máxima velocidad hacia la portería rival (100, 30)
    apply_intentions(state, {FORWARD_HOME: _run_to(Point2D(100, 30))})

    # Avanza exactamente 2 metros sobre el eje X
    assert state.players[FORWARD_HOME].position.x == pytest.approx(posicion_inicial.x + 2.0)
    assert state.players[FORWARD_HOME].position.y == pytest.approx(posicion_inicial.y)


def test_deberia_run_to_mover_solo_al_jugador_que_corre():
    # Tomamos nota de la ubicación de los otros 5 futbolistas
    state = _state()
    posiciones_demas_jugadores = {pid: p.position for pid, p in state.players.items() if pid != FORWARD_HOME}

    # Únicamente el delantero local ejecuta la orden de correr
    apply_intentions(state, {FORWARD_HOME: _run_to(Point2D(100, 30))})

    # Confirmamos que el resto del plantel permaneció congelado en sus puestos
    assert {pid: p.position for pid, p in state.players.items() if pid != FORWARD_HOME} == posiciones_demas_jugadores


def test_deberia_run_to_no_cambiar_la_velocidad_de_la_pelota():
    # Le imprimimos a la pelota una velocidad previa de rodaje.
    state = _state()
    state.ball.velocity = Vector2D(2.0, 3.0)

    # El delantero corre hacia el frente sin tocar el balón.
    apply_intentions(state, {FORWARD_HOME: _run_to(Point2D(100, 30))})

    # La trayectoria de la pelota debe ser independiente del movimiento del jugador.
    assert state.ball.velocity == Vector2D(2.0, 3.0)


def test_deberia_varios_run_to_en_el_mismo_tick_moverse_todos():
    # Posicionamos a los atacantes de ambos bandos.
    state = _state()
    pos_home_inicial = state.players[FORWARD_HOME].position
    pos_away_inicial = state.players[FORWARD_AWAY].position

    # Ambos delanteros corren al mismo tiempo hacia los arcos opuestos.
    apply_intentions(
        state,
        {FORWARD_HOME: _run_to(Point2D(100, 30)), FORWARD_AWAY: _run_to(Point2D(0, 30))},
    )

    # HOME avanzó hacia la derecha (+X) y AWAY avanzó hacia la izquierda (-X)
    assert state.players[FORWARD_HOME].position.x > pos_home_inicial.x
    assert state.players[FORWARD_AWAY].position.x < pos_away_inicial.x



# SECCIÓN 3: ACCIÓN KICK_BALL (REMATE Y CONTROLES)

def test_deberia_kick_ball_en_alcance_cambiar_la_velocidad_de_la_pelota():
    # Acomodamos la pelota a 1 metro de distancia del delantero.
    state = _state_con_pelota_junto_al(FORWARD_HOME, 1.0)

    # Patea la pelota hacia arriba (eje Y) con el 100% de potencia
    apply_intentions(state, {FORWARD_HOME: _kick(Vector2D(0, 1))})

    # La velocidad horizontal es cero y la vertical asciende al tope máximo de su atributo
    assert state.ball.velocity.x == pytest.approx(0.0)
    assert state.ball.velocity.y == pytest.approx(MAX_KICK_SPEED)


def test_deberia_kick_ball_mover_la_pelota_en_el_mismo_tick():
    # La pelota se encuentra a 1 m del atacante
    state = _state_con_pelota_junto_al(FORWARD_HOME, 1.0)
    posicion_balon_previa = state.ball.position

    # Patea fuerte hacia el frente (+X)
    apply_intentions(state, {FORWARD_HOME: _kick(Vector2D(1, 0))})

    # En este mismo tick, la pelota ya debe avanzar en X
    assert state.ball.position.x == pytest.approx(posicion_balon_previa.x + MAX_KICK_SPEED * TICK_DURATION_SECONDS)
    assert state.ball.position.y == pytest.approx(posicion_balon_previa.y)


def test_deberia_kick_ball_no_mover_al_jugador_que_patea():
    # Registramos la posición inicial del pateador
    state = _state_con_pelota_junto_al(FORWARD_HOME, 1.0)
    posicion_jugador_inicial = state.players[FORWARD_HOME].position

    # El jugador suelta el remate
    apply_intentions(state, {FORWARD_HOME: _kick(Vector2D(1, 0))})

    # Patear no altera las coordenadas físicas del cuerpo del jugador
    assert state.players[FORWARD_HOME].position == posicion_jugador_inicial


def test_deberia_kick_ball_fuera_de_alcance_dejar_la_pelota_sin_cambios():
    # Alejamos la pelota a 1.635 m (apenas 1 cm fuera de su radio de alcance de 1.625 m)
    state = _state_con_pelota_junto_al(FORWARD_HOME, REACH + 0.01)
    state.ball.velocity = Vector2D(1.0, 2.0)  # Venía rodando despacio

    # Intenta patear pero no llega a impactar
    apply_intentions(state, {FORWARD_HOME: _kick(Vector2D(1, 0))})

    # La pelota ignora la intención y mantiene intacta su marcha previa
    assert state.ball.velocity == Vector2D(1.0, 2.0)


def test_deberia_kick_ball_justo_en_el_borde_del_alcance_patear():
    # Colocamos la pelota justo sobre el radio exacto de su reach (1.625 m)
    state = _state_con_pelota_junto_al(FORWARD_HOME, REACH)

    # Intenta el disparo en el límite
    apply_intentions(state, {FORWARD_HOME: _kick(Vector2D(1, 0))})

    # El radio se detecta: el disparo se ejecuta correctamente.
    assert state.ball.velocity.x == pytest.approx(MAX_KICK_SPEED)


def test_deberia_kick_ball_con_power_percentage_cero_dejar_la_pelota_sin_velocidad():
    # Viene una pelota rápido a (3, 4) m/s
    state = _state_con_pelota_junto_al(FORWARD_HOME, 1.0)
    state.ball.velocity = Vector2D(3.0, 4.0)

    # El jugador amortigua o "pisa" la pelota pateando al 0% de potencia
    apply_intentions(state, {FORWARD_HOME: _kick(Vector2D(1, 0), 0.0)})

    # La pelota queda totalmente quieta.
    assert state.ball.velocity.magnitude() == pytest.approx(0.0)


def test_deberia_kick_ball_con_la_pelota_lejos_de_todos_no_hacer_nada():
    # Pelota en el centro pero ningún jugador cerca
    state = _state()

    # Todos envían intenciones de patear al aire
    apply_intentions(state, {pid: _kick(Vector2D(1, 0)) for pid in state.on_pitch_player_ids()})

    # Nadie tiene alcance, por lo cual el balón continúa sin velocidad
    assert state.ball.velocity == Vector2D(0.0, 0.0)


def test_deberia_kick_ball_medir_el_alcance_con_el_control_de_quien_patea():
    # Escenario A: Delantero estrella con CONTROL=100 intenta alcanzar una pelota lejana (a 3 m)
    state_crack = _state_con_pelota_junto_al(FORWARD_HOME, 3.0)
    state_crack.players[FORWARD_HOME].attributes[AttributeType.CONTROL] = 100
    apply_intentions(state_crack, {FORWARD_HOME: _kick(Vector2D(1, 0))})
    velocidad_crack = state_crack.ball.velocity

    # Escenario B: Delantero común (CONTROL=40) intenta llegar a esa misma pelota distante a 3 m
    state_normal = _state_con_pelota_junto_al(FORWARD_HOME, 3.0)
    apply_intentions(state_normal, {FORWARD_HOME: _kick(Vector2D(1, 0))})
    velocidad_normal = state_normal.ball.velocity

    # El jugador habilidoso alcanza a conectar el remate, mientras que el jugador común no la llega a rozar
    assert velocidad_crack.magnitude() > 0
    assert velocidad_normal.magnitude() == 0


def test_deberia_kick_ball_de_un_rival_tambien_mover_la_pelota():
    # Probamos la misma lógica de disparo pero ejecutada por el delantero visitante
    state = _state_con_pelota_junto_al(FORWARD_AWAY, 1.0)

    # Remata hacia la portería de HOME (-X)
    apply_intentions(state, {FORWARD_AWAY: _kick(Vector2D(-1, 0))})

    # La pelota sale disparada a máxima velocidad en dirección negativa
    assert state.ball.velocity.x == pytest.approx(-MAX_KICK_SPEED)

# SECCIÓN 4: RESOLUCIÓN DE DISPUTAS Y SIMULTANEIDAD

# AUXILIAR

def _state_con_dos_a_alcance():
    # Ponemos la pelota dividida con HOME (102) y AWAY (202) a 1 metro de ella
    state = _state_con_pelota_junto_al(FORWARD_HOME, 1.0)
    state.players[FORWARD_AWAY].position = Point2D(state.ball.position.x, state.ball.position.y + 1.0)
    return state


def test_deberia_dos_patadas_en_el_mismo_tick_ganar_el_player_id_mas_alto():
    # Dos rivales entran al choque intentando patear en direcciones opuestas en el mismo tick
    state = _state_con_dos_a_alcance()

    # HOME intenta enviar la pelota a +X y AWAY a -X
    apply_intentions(state, {FORWARD_HOME: _kick(Vector2D(1, 0)), FORWARD_AWAY: _kick(Vector2D(-1, 0))})

    # El motor desempata otorgando la prioridad al ID numéricamente superior (AWAY = 202)
    assert state.ball.velocity.x == pytest.approx(-MAX_KICK_SPEED)


def test_deberia_resultado_de_dos_patadas_no_depender_del_orden_del_diccionario():
    # Creamos dos instancias duplicadas del duelo
    a = _state_con_dos_a_alcance()
    b = _state_con_dos_a_alcance()

    # Insertamos las intenciones en orden invertido en cada diccionario
    apply_intentions(a, {FORWARD_HOME: _kick(Vector2D(1, 0)), FORWARD_AWAY: _kick(Vector2D(-1, 0))})
    apply_intentions(b, {FORWARD_AWAY: _kick(Vector2D(-1, 0)), FORWARD_HOME: _kick(Vector2D(1, 0))})

    # La física es totalmente determinista y produce exactamente la misma velocidad resultante.
    # Pues es el mismo escenario con las mismas intenciones, solo que en distinto orden de 
    # diccionario.
    assert a.ball.velocity == b.ball.velocity


def test_deberia_patada_fuera_de_alcance_no_pisar_la_patada_de_otro():
    # HOME está junto al balón pero AWAY (con ID mayor) tira una patada desde muy lejos
    state = _state_con_pelota_junto_al(FORWARD_HOME, 1.0)

    # Se registran las intenciones de patear de HOME y AWAY.
    apply_intentions(state, {FORWARD_HOME: _kick(Vector2D(1, 0)), FORWARD_AWAY: _kick(Vector2D(-1, 0))})

    # La patada inválida de AWAY se descarta y prevalece el remate efectivo de HOME
    assert state.ball.velocity.x == pytest.approx(MAX_KICK_SPEED)


def test_deberia_correr_y_patear_en_el_mismo_tick_aplicar_las_dos_cosas():
    # HOME patea la pelota al arco mientras AWAY retrocede corriendo
    state = _state_con_pelota_junto_al(FORWARD_HOME, 1.0)
    pos_inicial_rival = state.players[FORWARD_AWAY].position

    # Se aplican las intenciones de ambos
    apply_intentions(state, {FORWARD_HOME: _kick(Vector2D(1, 0)), FORWARD_AWAY: _run_to(Point2D(0, 30))})

    # Ambos sucesos se aplican armónicamente en el tick: la pelota sale disparada y el rival retrocede
    assert state.ball.velocity.x == pytest.approx(MAX_KICK_SPEED)
    assert state.players[FORWARD_AWAY].position.x < pos_inicial_rival.x

# SECCIÓN 5: MOVIMIENTO LIBRE DE PELOTA Y DETECCIÓN DE GOL

def test_deberia_pelota_en_movimiento_avanzar_velocidad_por_duracion_del_tick():
    # Pelota viajando libremente a (4, -2) m/s
    state = _state()
    state.ball.velocity = Vector2D(4.0, -2.0)

    # Transcurre el tick sin intenciones
    apply_intentions(state, {})

    # Avanza la distancia correspondiente: velocidad * duracion (0.5 s)
    assert state.ball.position.x == pytest.approx(BALL_INITIAL_POSITION.x + 4.0 * TICK_DURATION_SECONDS)
    assert state.ball.position.y == pytest.approx(BALL_INITIAL_POSITION.y - 2.0 * TICK_DURATION_SECONDS)


def test_deberia_pelota_quieta_quedarse_donde_esta():
    # Pelota estática en el origen
    state = _state()

    apply_intentions(state, {})

    # Mantiene la posición previa
    assert state.ball.position == BALL_INITIAL_POSITION


def test_deberia_pelota_patada_hacia_el_arco_terminar_dentro_y_run_tick_contar_el_gol():
    # Pelota a medio metro de la línea del arco visitante (x=104) y el delantero listo para empujarla
    state = _state()
    state.ball.position = Point2D(104.0, 30.0)
    state.players[FORWARD_HOME].position = Point2D(103.5, 30.0)

    # Corremos el tick completo donde el atacante remata e impacta.
    run_tick(
        state,
        execute_behavior=_behavior_que_patea(Vector2D(1, 0), 1.0),
        apply_intentions=apply_intentions,
        detect_goal=detect_goal,
    )

    # Hay gol y suma al marcador de HOME
    assert state.score.home == 1

# Dos situaciones, para testear que se detiene en ambos arcos, tanto AWAY como HOME
# cuando el disparo es muy fuerte
@pytest.mark.parametrize(
    "inicio, velocidad, lado_que_convierte, linea_x",
    [
        (Point2D(10.7, 30.0), Vector2D(-28.9, 8.1), TeamSide.AWAY, 0.0), # Patea fuerte AWAY
        (Point2D(94.3, 30.0), Vector2D(28.9, 8.1), TeamSide.HOME, 105.0), # Patea fuerte HOME
    ],
)
def test_deberia_pelota_que_cruza_el_arco_en_un_tick_quedar_quieta_en_la_linea_y_contar_gol(
    inicio, velocidad, lado_que_convierte, linea_x
):
    # Disparo de alta velocidad que atravesaría la línea final durante el intervalo del tick
    state = _state()
    state.ball.position = inicio
    state.ball.velocity = velocidad

    # No se registran intenciones
    apply_intentions(state, {})

    # El motor atrapa la pelota justo en el plano del arco (linea_x), anula su velocidad y detecta el gol.
    assert state.ball.position.x == pytest.approx(linea_x)
    assert state.ball.velocity == Vector2D(0.0, 0.0)
    assert detect_goal(state.ball.position) == lado_que_convierte

# SECCIÓN 6: REINICIO Y REORIENTACIÓN POST-GOL

# Coordenadas donde se coloca la pelota tras un gol 
# (desplazado en el centro hacia el equipo que lo recibió)
SAQUE_DE_HOME = Point2D(BALL_INITIAL_POSITION.x - KICKOFF_OFFSET, BALL_INITIAL_POSITION.y)
SAQUE_DE_AWAY = Point2D(BALL_INITIAL_POSITION.x + KICKOFF_OFFSET, BALL_INITIAL_POSITION.y)


@pytest.mark.parametrize(
    "posicion, saque_esperado",
    [
        (Point2D(0.0, 30.0), SAQUE_DE_HOME),     # Gol en el arco local -> saca HOME
        (Point2D(-1.0, 30.0), SAQUE_DE_HOME),    # Pelota tras la red local -> saca HOME
        (Point2D(105.0, 30.0), SAQUE_DE_AWAY),   # Gol en el arco visitante -> saca AWAY
        (Point2D(106.0, 28.0), SAQUE_DE_AWAY),   # Pelota tras la red visitante -> saca AWAY
    ],
)
def test_deberia_pelota_en_un_arco_volver_a_la_linea_central_corrida_hacia_el_que_recibio_el_gol(posicion, saque_esperado):
    # La pelota quedó adentro del arco en el paso anterior
    state = _state()
    state.ball.position = posicion
    state.ball.velocity = Vector2D(5.0, 5.0)

    # El motor procesa el inicio del tick y detecta la necesidad de reiniciar
    apply_intentions(state, {})

    # La pelota aparece reseteada en la zona central asignada al equipo perdedor y totalmente detenida
    assert state.ball.position == saque_esperado
    assert state.ball.velocity == Vector2D(0.0, 0.0)


@pytest.mark.parametrize(
    "posicion",
    [
        Point2D(0.0, 5.0),    # Saque de meta / línea de fondo afuera del arco
        Point2D(50.0, 30.0),  # Mediocampo
        Point2D(100.0, 30.0), # Área rival pero aún en juego
    ],
)
def test_deberia_pelota_fuera_de_un_arco_no_reiniciarse(posicion):
    # La pelota está en juego y fuera del arco
    state = _state()
    state.ball.position = posicion
    state.ball.velocity = Vector2D(5.0, 5.0)

    apply_intentions(state, {})

    # No hay reinicio por gol: la pelota simplemente rueda según su física normal
    assert state.ball.velocity == Vector2D(5.0, 5.0)
    assert state.ball.position.x == pytest.approx(posicion.x + 5.0 * TICK_DURATION_SECONDS)
    assert state.ball.position.y == pytest.approx(posicion.y + 5.0 * TICK_DURATION_SECONDS)


def test_deberia_reiniciar_la_pelota_antes_de_resolver_las_patadas():
    # Tras un gol, la pelota va al centro y el atacante ya se ubicó listo al lado del nuevo punto de saque
    state = _state()
    state.ball.position = Point2D(0.0, 30.0)
    state.players[FORWARD_HOME].initial_position = Point2D(SAQUE_DE_HOME.x - 1.0, SAQUE_DE_HOME.y)

    # Patea la pelota inmediatamente en este mismo tick de reinicio
    apply_intentions(state, {FORWARD_HOME: _kick(Vector2D(1, 0))})

    # El reinicio ocurre primero, permitiendo que la patada conecte con el balón en su nueva posición del centro
    assert state.ball.position.x == pytest.approx(SAQUE_DE_HOME.x + MAX_KICK_SPEED * TICK_DURATION_SECONDS)
    assert state.ball.velocity.x == pytest.approx(MAX_KICK_SPEED)


def _state_con_los_jugadores_lejos_de_su_posicion_inicial():
    """Desplaza a los 6 titulares varios metros lejos de sus posiciones tácticas."""
    state = _state()
    iniciales = {pid: p.position for pid, p in state.players.items() if p.position is not None}
    for jugador in state.players.values():
        if jugador.position is not None:
            jugador.position = Point2D(jugador.position.x + 7.0, jugador.position.y - 3.0)
    return state, iniciales


def test_deberia_devolver_a_todos_los_jugadores_en_cancha_a_su_posicion_inicial_tras_un_gol():
    # Los futbolistas estaban desordenados en el campo tras la jugada del gol
    state, iniciales = _state_con_los_jugadores_lejos_de_su_posicion_inicial()
    state.ball.position = Point2D(0.0, 30.0) # Hubo gol en el lado izquierdo del campo.

    # Se aplica la rutina de reinicio por gol
    apply_intentions(state, {})

    # Todos los titulares en cancha se teletransportan a sus puestos de formación táctica inicial
    assert {pid: p.position for pid, p in state.players.items() if p.position is not None} == iniciales
    assert len(iniciales) == 6


def test_deberia_no_reubicar_a_un_jugador_fuera_de_cancha_aunque_tenga_posicion_inicial():
    # Un jugador que está en el banco (position=None)
    state = _state()
    state.players[FORWARD_HOME].position = None
    state.ball.position = Point2D(0.0, 30.0)

    apply_intentions(state, {})

    # El reinicio respeta que sigue estando fuera del terreno de juego
    assert state.players[FORWARD_HOME].position is None


def test_deberia_el_jugador_correr_desde_su_posicion_inicial_en_el_tick_del_reinicio():
    # Luego de convertirse un gol, el jugador arranca corriendo hacia un objetivo durante 
    # el mismo tick de reinicio.
    state, iniciales = _state_con_los_jugadores_lejos_de_su_posicion_inicial()
    state.ball.position = Point2D(0.0, 30.0) # Hubo gol en el lado izquierdo del campo.
    inicial = iniciales[FORWARD_HOME]
    destino = Point2D(inicial.x + 10.0, inicial.y)

    apply_intentions(state, {FORWARD_HOME: _run_to(destino)})

    # El paso recorrido se calcula usando como partida su puesto de formación táctica reseteado
    paso = state.players[FORWARD_HOME].position.distance_to(inicial)
    assert 0.0 < paso <= MAX_RUN_SPEED_METERS_PER_SECOND * TICK_DURATION_SECONDS + 1e-9


@pytest.mark.parametrize(
    "arco_donde_entra, lado_que_recibe",
    [
        (Point2D(0.0, 30.0), TeamSide.HOME),
        (Point2D(105.0, 30.0), TeamSide.AWAY),
    ],
)
def test_deberia_tocar_primero_el_equipo_que_recibio_el_gol(arco_donde_entra, lado_que_recibe):
    # Les asignamos comportamiento de ataque a los jugadores para que busquen activamente el balón
    state = _state()
    for jugador in state.players.values():
        assign_behavior(jugador, 1, OFENSIVE)
    state.ball.position = arco_donde_entra

    # Hacemos correr la simulación hasta que alguno patee el balón
    for _ in range(40):
        run_tick(state, execute_behavior=execute_behavior, apply_intentions=apply_intentions, detect_goal=detect_goal)
        if state.ball.velocity != Vector2D(0.0, 0.0):
            break

    # El primer equipo en patear la pelota tras el saque debe ser el que acaba de encajar el gol
    pateo_home = state.ball.velocity.x > 0
    assert state.ball.velocity != Vector2D(0.0, 0.0) # chequea que alguien tiene que haber pateado
    assert pateo_home == (lado_que_recibe is TeamSide.HOME)

# SECCIÓN 7: TRATAMIENTO DE SUPLENTES EN EL BANCO

def test_deberia_ignorar_la_intencion_de_un_suplente():
    # Un suplente (fuera de cancha) intenta ejecutar un desplazamiento
    state = _state()

    apply_intentions(state, {SUBSTITUTE_HOME: _run_to(Point2D(50, 30))})

    # La simulación ignora su orden y no le asigna posición física en cancha
    assert state.players[SUBSTITUTE_HOME].position is None

# SECCIÓN 8: INTEGRACIÓN CON RUN_TICK Y PLAYER_API

# AUXILIARES

def _no_goal(state):
    # Mock para no detectar goles.
    return None


def _behavior_que_patea(direction, power_percentage):
    # Fabrica un comportamiento falso que genera la intención de patear en la dirección y 
    # potencia indicadas.
    def execute(state, player_id):
        game_state, attributes = build_player_snapshot(state, player_id)
        api = PlayerAPI(game_state, attributes)
        api.kick_ball(direction, power_percentage)
        return api.intention
    return execute


def test_deberia_run_tick_con_kick_ball_real_cambiar_la_velocidad_y_avanzar_el_tick():
    # Probamos el flujo extremo a extremo: la API arma la intención y run_tick la aplica
    state = _state_con_pelota_junto_al(FORWARD_HOME, 1.0)

    # Ejecutamos el tick completo con la intención de patear hacia el frente (+X) 
    # con 100% de potencia.
    run_tick(
        state,
        execute_behavior=_behavior_que_patea(Vector2D(1, 0), 1.0),
        apply_intentions=apply_intentions,
        detect_goal=_no_goal,
    )

    # Comprobamos que se aceleró la pelota, el jugador registró su acción actual KICK_BALL y se incrementó el tick
    assert state.ball.velocity.x == pytest.approx(MAX_KICK_SPEED)
    assert state.players[FORWARD_HOME].current_action == ActionType.KICK_BALL
    assert state.current_tick == 1


def test_deberia_kick_ball_invalido_no_interrumpir_el_ciclo_del_partido():
    # El comportamiento intenta pasar un parámetro inválido (potencia al 500%)
    state = _state_con_pelota_junto_al(FORWARD_HOME, 1.0)

    # Se corre el tick completo con la intención de patear hacia el frente (+X)
    run_tick(
        state,
        execute_behavior=_behavior_que_patea(Vector2D(1, 0), 5.0),
        apply_intentions=apply_intentions,
        detect_goal=_no_goal,
    )

    # Se captura la anomalía limpiamente: la pelota no adquiere velocidad, el jugador pasa a IDLE 
    # y el tick avanza sin errores.
    assert state.ball.velocity == Vector2D(0.0, 0.0)
    assert state.players[FORWARD_HOME].current_action == ActionType.IDLE
    assert state.current_tick == 1