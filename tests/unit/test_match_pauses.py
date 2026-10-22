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
from src.engine._01_to_world.data_types import ActionType, Intention
from src.engine._01_to_world.metrics import PauseType, pause_schedule_for
from src.engine._02_to_match.state import MatchPhase, MatchRegistry, MatchState
from src.engine.match_runner import run_match
from tests.unit.test_match_runner import _build_state

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

# --- test de Eventos de pausa ---

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