"""
Tests de la ejecución de la tanda de penales (play_shootout) y de su enganche en run_match.
"""

from unittest.mock import AsyncMock, Mock, call

import pytest

from src.engine import penalties
from src.engine._01_to_world.metrics import PENALTY_MAX_ROUNDS, PENALTY_MAX_TICKS
from src.engine._01_to_world.pitch import TeamSide
from src.engine._02_to_match.state import MatchPhase, MatchRegistry
from src.engine.match_runner import run_match
from src.engine.penalties import play_shootout

# Reutiliza el estado de prueba del motor: el equipo 1 es el host (HOME) y el 2 el visitante
from tests.unit.test_match_runner import _build_state

# Es el LADO que convierte el gol en la tanda. Como siempre se patea contra el mismo arco (izq), 
# no importa quien convirtió: lo importante es que sea el mismo lado para ambos equipos.
GOL = TeamSide.AWAY 

SIN_GOL = None


async def _jugar_tanda(state, detect_goal, notify=None, pausa=0, preparacion=0):
    """
    Juega la tanda con el detect_goal que se le pasa y el resto de las piezas en Mock.
    Por defecto no espera nada (pausa entre penales y espera de preparación en 0) para que los tests sean rápidos.
    """
    await play_shootout(
        state,
        execute_behavior=Mock(),
        apply_intentions=Mock(),
        detect_goal=detect_goal,
        notify=notify if notify is not None else AsyncMock(),
        tick_interval_seconds=0,
        penalty_pause_seconds=pausa,
        penalty_setup_seconds=preparacion,
    )


async def _jugar_partido(state, **extra):
    """Juega el partido completo con las piezas en Mock. 'extra' son los parámetros de la tanda y del guardado."""
    await run_match(
        state,
        MatchRegistry(),
        execute_behavior=Mock(),
        apply_intentions=Mock(),
        detect_goal=Mock(return_value=SIN_GOL),
        notify=AsyncMock(),
        tick_interval_seconds=0,
        **extra,
    )

@pytest.mark.asyncio
async def test_deberia_ganar_el_host_y_terminar_la_tanda_si_convierte_solo_el_en_la_primera_ronda(monkeypatch):
    state = _build_state()
    # Para que cada penal dure un solo tick, tenga gol o no: así cada valor de detect_goal es un penal
    monkeypatch.setattr(penalties, "PENALTY_MAX_TICKS", 1)
    # Ronda 1: el host patea y convierte; el visitante patea y no convierte
    # side_effect devuelve un valor por cada llamada: la primera vez devuelve GOL, la segunda SIN_GOL.
    detect_goal = Mock(side_effect=[GOL, SIN_GOL])

    await _jugar_tanda(state, detect_goal)

    assert (state.score.phome, state.score.paway) == (1, 0)  # gana el host
    assert detect_goal.call_count == 2                       # y no se jugó una segunda ronda

    # (De forma análoga, se podría comprobar con el visitante.)

@pytest.mark.asyncio
async def test_deberia_sortear_al_host_y_sumarle_un_gol_si_siguen_empatados_despues_de_3_rondas(monkeypatch):
    state = _build_state()
    # El sorteo lo gana el host
    monkeypatch.setattr(penalties.random, "choice", Mock(return_value=state.host_team_id))
    detect_goal = Mock(return_value=SIN_GOL)  # nadie convierte nunca

    await _jugar_tanda(state, detect_goal)

    # Se jugaron las 3 rondas completas: 2 penales por ronda, cada uno de PENALTY_MAX_TICKS ticks sin gol
    assert detect_goal.call_count == PENALTY_MAX_ROUNDS * 2 * PENALTY_MAX_TICKS
    assert (state.score.phome, state.score.paway) == (1, 0)  # el sorteo lo ganó el host

    # (De forma análoga, se podría comprobar con el visitante.)

# Se eligió utilizar una función con una tanda falsa por el hecho de que es la forma que tenemos de 
# comprobar que run_match llama a la tanda antes de pasar a FINISHED.
@pytest.mark.asyncio
async def test_deberia_jugar_la_tanda_antes_de_pasar_a_finished_si_empata_con_penales_habilitados():
    state = _build_state(total_ticks=1) # el único tick no tiene goles: el partido termina 0-0
    state.penalties_enabled = True  

    # La tanda de mentira deja un resultado de penales en el estado, como lo haría la de verdad.
    # run_match llama a la tanda pasándole las piezas del motor (execute_behavior, apply_intentions,
    # detect_goal, notify y tick_interval_seconds) por nombre, así que este fake tiene que aceptarlas
    # aunque no las use: por eso recibe **_, que en Python es la forma de decir "se ignoran a propósito".
    async def jugar_tanda(state, **_):
        state.score.phome, state.score.paway = 2, 1

    # Al guardar, anotamos cómo estaba el partido en ese momento
    guardado = []

    def on_finished(state):
        guardado.append((state.phase, state.score.phome, state.score.paway))

    await _jugar_partido(state, play_shootout=jugar_tanda, on_finished=on_finished)

    # Cuando se guardó el resultado, el partido estaba FINISHED y la tanda ya se había jugado
    assert guardado == [(MatchPhase.FINISHED, 2, 1)]

@pytest.mark.asyncio
async def test_deberia_sumar_el_gol_al_equipo_pateador_aunque_el_arco_sea_el_mismo_para_ambos(monkeypatch):
    state = _build_state()
    monkeypatch.setattr(penalties, "PENALTY_MAX_TICKS", 1)  # cada penal dura un solo tick
    # Ronda 1: el host patea y no convierte; el visitante patea y convierte
    detect_goal = Mock(side_effect=[SIN_GOL, GOL])

    await _jugar_tanda(state, detect_goal)

    # Los dos patean contra el mismo arco, pero el gol es del visitante
    assert (state.score.phome, state.score.paway) == (0, 1)

    # (De forma análoga, se podría comprobar con el host convirtiendo.)

@pytest.mark.asyncio
async def test_deberia_avisar_como_quedaron_ubicados_los_jugadores_antes_de_jugar_el_primer_tick(monkeypatch):
    state = _build_state()
    monkeypatch.setattr(penalties, "PENALTY_MAX_TICKS", 1)  # cada penal dura un solo tick
    notify = AsyncMock()
    detect_goal = Mock(side_effect=[GOL, SIN_GOL])
    # Un Mock "padre" que anota en qué orden se llamó a notify y a detect_goal (que se llama una vez por tick)
    orden = Mock()
    orden.attach_mock(notify, "aviso")
    orden.attach_mock(detect_goal, "tick")

    await _jugar_tanda(state, detect_goal, notify=notify)

    # En cada penal primero va el aviso de preparación (jugadores en su lugar, pelota quieta),
    # y después el tick con su aviso. Dos penales, entonces: aviso, tick, aviso, aviso, tick, aviso
    assert [nombre for nombre, _args, _kwargs in orden.mock_calls] == ["aviso", "tick", "aviso", "aviso", "tick", "aviso"]


@pytest.mark.asyncio
async def test_deberia_esperar_antes_de_cada_patada_con_los_jugadores_ya_ubicados(monkeypatch):
    state = _build_state()
    monkeypatch.setattr(penalties, "PENALTY_MAX_TICKS", 1)  # cada penal dura un solo tick
    sleep = AsyncMock()
    monkeypatch.setattr(penalties.asyncio, "sleep", sleep)  # no espera de verdad: solo anota cuánto le pidieron
    detect_goal = Mock(side_effect=[GOL, SIN_GOL])  # ronda 1: dos penales

    await _jugar_tanda(state, detect_goal, pausa=3.0, preparacion=1.5)

    # Una espera de preparación por penal (2). La pausa de 3 s es entre penales, no es esta espera
    assert sleep.await_args_list.count(call(1.5)) == 2


@pytest.mark.asyncio
async def test_deberia_seguir_la_tanda_aunque_falle_el_aviso(monkeypatch):
    state = _build_state()
    monkeypatch.setattr(penalties, "PENALTY_MAX_TICKS", 1)  # cada penal dura un solo tick
    notify = AsyncMock(side_effect=RuntimeError("falla simulada"))  # cada aviso lanza un error
    detect_goal = Mock(side_effect=[GOL, SIN_GOL])

    await _jugar_tanda(state, detect_goal, notify=notify)

    assert (state.score.phome, state.score.paway) == (1, 0)  # la tanda se jugó igual y ganó el host


"""
Los guardados (save_match_result y make_on_finished) se prueban en test_match_start_service.py

Así como que la pelota se quede quieta en la linea del arco se prueba en test_simulation.py
"""