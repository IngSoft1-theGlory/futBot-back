"""
Conversión entre match_duration (minutos, lo que elige el usuario:
2 o 5 — ya validado en lineup_service) y los parámetros que necesita
el motor: total_ticks y tick_interval_seconds.

Decisión de diseño: 1 tick = 0.5 segundos.
Esto fija a la vez dos cosas distintas, a propósito:
  - cuánto tiempo de partido simula cada tick (para calcular total_ticks)
  - cada cuánto tiempo REAL se emite un tick (el ritmo del WS)
Si en algún momento se quiere que el servidor simule más rápido que
tiempo real (por ejemplo, para pruebas), tick_interval_seconds y
TICK_DURATION_SECONDS pueden desacoplarse: run_match ya los recibe
como parámetros separados, no hace falta tocar match_runner.py.
"""

TICK_DURATION_SECONDS = 0.5

VALID_MATCH_DURATIONS_MINUTES = (2, 5)


def total_ticks_for(match_duration_minutes: int) -> int:
    """
    match_duration_minutes: 2 o 5 (contrato de API, INVALID_SETTINGS
    si no). Acá no se revalida -- esa validación ya la hace
    lineup_service antes de llegar a este punto; si llega un valor
    fuera de rango es un bug de ese chequeo, no un caso a manejar acá.

    2 minutos -> 240 ticks. 5 minutos -> 600 ticks (el máximo).
    """
    return int(match_duration_minutes * 60 / TICK_DURATION_SECONDS)
