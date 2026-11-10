"""
Tests de las pausas del partido (Cooling Break y Half-Time).

Cómo se "espía" una pausa sin esperarla: el motor se duerme con asyncio.sleep
(0 s entre ticks, 10 o 20 s en una pausa). En estos tests se reemplaza
asyncio.sleep por una función que NO espera y solo anota qué ve el partido en
ese momento. Como tick_interval_seconds=0, toda espera mayor a 0 es una pausa.
"""

from dataclasses import dataclass
from unittest.mock import Mock

import pytest

from src.engine import match_runner
from src.engine._01_to_world.data_types import ActionType, Intention, Point2D, Vector2D
from src.engine._01_to_world.metrics import PauseSlot, PauseType, pause_schedule_for
from src.engine._01_to_world.pitch import BALL_INITIAL_POSITION, detect_goal
from src.engine._02_to_match.state import MatchPhase, MatchRegistry, MatchState, swap_sides
from src.engine._03_to_builder.snapshot import build_player_snapshot
from src.engine.match_runner import _run_pause, run_match, run_tick
from tests.unit.test_match_runner import _build_state, _idle_behavior, _noop_apply

JUGADORES_EN_CANCHA = 6  # 3 titulares por equipo (ver _build_state)


@dataclass
class PausaVista:
    """Lo que se vio justo cuando el motor empezó a esperar una pausa."""
    segundos: float
    fase: MatchPhase
    tick: int
    comportamientos_ejecutados: int
    ticks_notificados: int


@dataclass
class PartidoJugado:
    state: MatchState
    pausas: list[PausaVista]
    ticks_notificados: list[int]       # current_tick de cada TICK_UPDATE enviado, en orden
    estados_notificados: list[tuple]   # (phase, pause) que tenía el partido en cada TICK_UPDATE
    resultados_guardados: list[MatchState]
    comportamientos_ejecutados: int


async def _jugar_partido(monkeypatch, total_ticks: int = 240, notify_pause=None) -> PartidoJugado:
    """Juega un partido entero con piezas falsas y anota lo que pasa en cada pausa."""
    state = _build_state(total_ticks)
    pausas = []
    ticks_notificados = []
    estados_notificados = []
    resultados_guardados = []

    # Mock acepta cualquier argumento y cuenta cuántas veces lo llamaron.
    execute_behavior = Mock(return_value=Intention(ActionType.IDLE))

    async def notify(estado):
        ticks_notificados.append(estado.current_tick)
        estados_notificados.append((estado.phase, estado.pause))

    async def sleep_espia(segundos):
        # run_match se duerme en dos lugares: entre ticks (tick_interval_seconds=0 en este test)
        # y dentro de una pausa (10 o 20 s). Entonces, si le piden dormir más de 0 s, es una pausa.
        # No esperamos de verdad: solo anotamos qué ve el partido en ese momento.

        if segundos > 0:  # entre ticks espera 0 s, así que esto es una pausa
            pausas.append(PausaVista(
                segundos=segundos,
                fase=state.phase,
                tick=state.current_tick,
                comportamientos_ejecutados=execute_behavior.call_count,
                ticks_notificados=len(ticks_notificados),
            ))

    # Cambiamos asyncio.sleep por el espía durante este test (monkeypatch lo restaura al terminar)
    monkeypatch.setattr(match_runner.asyncio, "sleep", sleep_espia)

    # Se corre el partido con los Mocks.
    await run_match(
        state,
        MatchRegistry(),
        execute_behavior=execute_behavior,
        apply_intentions=Mock(),
        detect_goal=Mock(return_value=None),
        notify=notify,
        tick_interval_seconds=0,
        on_finished=resultados_guardados.append,
        notify_pause=notify_pause,
    )

    # Devolvemos lo ocurrido en el partido, para que los tests puedan hacer sus aserciones.
    return PartidoJugado(
        state, pausas, ticks_notificados, estados_notificados,
        resultados_guardados, execute_behavior.call_count,
    )

@pytest.mark.parametrize(
    "total_ticks, ticks_esperados",
    [(240, [60, 120, 180]), (600, [150, 300, 450])],
)
def test_deberia_pause_schedule_for_devolver_los_ticks_y_tipos_esperados(total_ticks, ticks_esperados):
    calendario = pause_schedule_for(total_ticks)

    assert [pausa.tick for pausa in calendario] == ticks_esperados
    assert [pausa.type for pausa in calendario] == [
        PauseType.COOLING_BREAK, PauseType.HALF_TIME, PauseType.COOLING_BREAK,
    ]
    assert [pausa.number for pausa in calendario] == [1, 2, 3]


@pytest.mark.parametrize("total_ticks", [1, 3, 5, 239, 1000])
def test_deberia_pause_schedule_for_devolver_lista_vacia_para_cualquier_otro_total(total_ticks):
    assert pause_schedule_for(total_ticks) == []

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "total_ticks, ticks_de_pausa",
    [(240, [60, 120, 180]), (600, [150, 300, 450])],
)
async def test_deberia_pasar_a_paused_con_el_reloj_detenido_en_cada_tick_de_pausa(
    monkeypatch, total_ticks, ticks_de_pausa
):
    partido = await _jugar_partido(monkeypatch, total_ticks)

    # el motor esperó 3 veces, justo en los ticks del calendario...
    assert [pausa.tick for pausa in partido.pausas] == ticks_de_pausa
    # ...con el partido en PAUSED...
    assert all(pausa.fase is MatchPhase.PAUSED for pausa in partido.pausas)
    # ...y durante lo que dice el calendario: Cooling Break 10 s, Half-Time 20 s
    assert [pausa.segundos for pausa in partido.pausas] == [10, 20, 10]

@pytest.mark.asyncio
async def test_deberia_no_ejecutar_comportamientos_ni_enviar_tick_update_durante_la_pausa(monkeypatch):
    partido = await _jugar_partido(monkeypatch)
    # Si la pausa ejecutara algo, estos números se adelantarían a los ticks jugados.

    for pausa in partido.pausas:
        assert pausa.comportamientos_ejecutados == pausa.tick * JUGADORES_EN_CANCHA
        assert pausa.ticks_notificados == pausa.tick

    # Y al final no sobra ni falta nada: 240 ticks, cada uno con sus comportamientos y su TICK_UPDATE
    assert partido.comportamientos_ejecutados == 240 * JUGADORES_EN_CANCHA
    assert len(partido.ticks_notificados) == 240

@pytest.mark.asyncio
async def test_deberia_volver_a_in_progress_seguir_desde_el_mismo_tick_y_pausar_una_sola_vez(monkeypatch):
    partido = await _jugar_partido(monkeypatch)

    # sigue desde el mismo tick: ningún tick se repite ni se saltea (el 60 va seguido del 61, etc.)
    assert partido.ticks_notificados == list(range(1, 241))
    # cada pausa ocurre una sola vez
    assert len(partido.pausas) == 3
    # fuera de las pausas el partido está en IN_PROGRESS y sin pause
    assert all(fase is MatchPhase.IN_PROGRESS and pausa is None for fase, pausa in partido.estados_notificados)

@pytest.mark.asyncio
async def test_deberia_terminar_en_finished_y_guardar_el_resultado_tras_las_3_pausas(monkeypatch):
    partido = await _jugar_partido(monkeypatch)

    assert len(partido.pausas) == 3
    assert partido.state.phase is MatchPhase.FINISHED
    assert partido.resultados_guardados == [partido.state]

@pytest.mark.asyncio
async def test_deberia_avisar_el_inicio_y_el_fin_de_cada_pausa_en_orden(monkeypatch):
    avisos = []

    async def notify_pause(state, tipo, duracion, started):
        # Guarda el estado del partido en cada aviso para comprobar
        # que la pausa ya esté activa al comenzar y ya haya terminado al finalizar
        avisos.append((tipo, duracion, started, state.phase, state.pause is not None))

    await _jugar_partido(monkeypatch, notify_pause=notify_pause)

    # Se usan nombres cortos para que la secuencia esperada sea más fácil de leer
    CB, HT = PauseType.COOLING_BREAK, PauseType.HALF_TIME
    EN_PAUSA, SIN_PAUSA = MatchPhase.PAUSED, MatchPhase.IN_PROGRESS
    # Cada pausa debe generar dos avisos: uno al comenzar y otro al terminar.
    # El orden esperado es Cooling Break, Half-Time y Cooling Break
    assert avisos == [ # tipo, duracion, started, fase, pause_activa
        (CB, 10, True, EN_PAUSA, True), (CB, 10, False, SIN_PAUSA, False),
        (HT, 20, True, EN_PAUSA, True), (HT, 20, False, SIN_PAUSA, False),
        (CB, 10, True, EN_PAUSA, True), (CB, 10, False, SIN_PAUSA, False),
    ]


@pytest.mark.asyncio
async def test_deberia_continuar_el_partido_si_falla_notify_pause(monkeypatch):
    llamadas = []  

    async def notify_pause_roto(state, tipo, duracion, started):
        llamadas.append(started)
        raise RuntimeError("falló el envío")

    # si falla el aviso, el motor debe completar las pausas y terminar el partido.
    partido = await _jugar_partido(monkeypatch, notify_pause=notify_pause_roto)

    assert len(llamadas) == 6 # se intentó avisar 2 veces por pausa (inicio y fin) y el partido siguió igual
    assert len(partido.pausas) == 3 # y las pausas se ejecutaron todas
    assert partido.ticks_notificados == list(range(1, 241)) # todos los ticks
    assert partido.state.phase is MatchPhase.FINISHED # y terminó el partido
    assert partido.resultados_guardados == [partido.state] # y guardó el resultado final


# --- Cambio de lados en el Half-Time ---
# Estos tests llaman a _run_pause con 0 segundos de espera y comparan el estado 
# del partido antes y después de la pausa.

COOLING_BREAK = PauseSlot(number=1, tick=60, type=PauseType.COOLING_BREAK)
HALF_TIME = PauseSlot(number=2, tick=120, type=PauseType.HALF_TIME)


@pytest.mark.asyncio
async def test_deberia_invertir_el_side_de_todos_los_jugadores_tras_el_half_time():
    state = _build_state()
    sides_antes = {pid: p.side for pid, p in state.players.items()}

    await _run_pause(state, HALF_TIME, 0)

    # Solo hay dos lados, así que "distinto al de antes" es "el lado contrario".
    for pid, jugador in state.players.items():  # titulares y suplentes
        assert jugador.side is not sides_antes[pid]


@pytest.mark.asyncio
async def test_deberia_dejar_a_los_titulares_en_su_posicion_inicial_espejada_y_la_pelota_en_el_centro():
    state = _build_state()
    # Posición inicial de cada titular (los suplentes no tienen).
    iniciales = {pid: p.initial_position for pid, p in state.players.items() if p.initial_position is not None}
    # Durante el primer tiempo un jugador se movió y la pelota viajó.
    state.players[100].position = Point2D(50.0, 20.0)
    state.ball.position = Point2D(10.0, 5.0)
    state.ball.velocity = Vector2D(3.0, 1.0)

    await _run_pause(state, HALF_TIME, 0)

    for pid, inicial in iniciales.items():
        # Espejar es girar 180 grados respecto del centro de la cancha.
        assert state.players[pid].position == Point2D(105 - inicial.x, 60 - inicial.y)
    assert state.ball.position == BALL_INITIAL_POSITION
    assert state.ball.velocity == Vector2D(0.0, 0.0)


# En los dos tests de gol, swap_sides deja el estado como al empezar el segundo tiempo:
# el anfitrión defiende x = 105 y ataca x = 0; el visitante, al revés.

def test_deberia_sumar_al_anfitrion_el_gol_en_x_0_del_segundo_tiempo():
    state = _build_state()
    swap_sides(state)
    state.ball.position = Point2D(0.0, 30.0)  # la pelota entra al arco al que ataca el anfitrión

    run_tick(state, execute_behavior=_idle_behavior, apply_intentions=_noop_apply, detect_goal=detect_goal)

    assert state.score.home == 1
    assert state.score.away == 0


def test_deberia_sumar_al_visitante_el_gol_en_x_105_del_segundo_tiempo():
    state = _build_state()
    swap_sides(state)
    state.ball.position = Point2D(105.0, 30.0)  # la pelota entra al arco al que ataca el visitante

    run_tick(state, execute_behavior=_idle_behavior, apply_intentions=_noop_apply, detect_goal=detect_goal)

    assert state.score.home == 0
    assert state.score.away == 1


def test_deberia_el_snapshot_reflejar_el_lado_nuevo_tras_el_cambio_de_lados():
    state = _build_state()
    anfitrion = 100  # titular del anfitrión (en el primer tiempo defendía x = 0)

    swap_sides(state)
    game_state, _ = build_player_snapshot(state, anfitrion)

    # Ahora defiende x = 105 y ataca x = 0.
    assert game_state.team_goal == Point2D(105.0, 30.0)
    assert game_state.opponent_goal == Point2D(0.0, 30.0)


@pytest.mark.asyncio
async def test_deberia_el_cooling_break_no_cambiar_lados_ni_posiciones():
    state = _build_state()
    antes = {pid: (p.side, p.position) for pid, p in state.players.items()}

    await _run_pause(state, COOLING_BREAK, 0)

    despues = {pid: (p.side, p.position) for pid, p in state.players.items()}
    assert despues == antes
