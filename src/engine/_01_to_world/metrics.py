"""
MACROS, Medidas, Valores Fijos
"""

from dataclasses import dataclass
from enum import Enum

# ==================================== Valores máximos ========================================

MAX_RUN_SPEED_METERS_PER_SECOND = 8.0       # Máximo recorrido por parte de un jugador en m/s.
MAX_ATTRIBUTE_VALUE = 100                   # Valor máximo que puede tener un atributo.
MAX_KICK_SPEED_METERS_PER_SECOND = 30.0     # Máxima potencia de disparo en m/s.


def reach_distance(control: int) -> float:
    """
    Devuelve la distancia máxima de interacción (en metros/unidades) calculada 
    dinámicamente por el servidor según el atributo CONTROL. 
    
    Ver más info. en Documentación - "ABOUT_FORMULAS"
    """
    return 0.05625 * control - 0.625


def kick_speed(power: int, power_percentage: float) -> float:
    """
    Rapidez (m/s) que un jugador le da a la pelota. Proporcional a power_percentage.
    
    Ver más info. en Documentación - "ABOUT_FORMULAS"
    """
    return MAX_KICK_SPEED_METERS_PER_SECOND * power / MAX_ATTRIBUTE_VALUE * power_percentage

# ======================================== Tiempos =============================================

TICK_DURATION_SECONDS = 0.5                 # Duración por Tick.
VALID_MATCH_DURATIONS_MINUTES = (2, 5)      # Duraciones válidas de partidos en minutos.

def total_ticks_for(match_duration_minutes: int) -> int:
    """
    match_duration_minutes: 2 o 5 

    2 minutos -> 240 ticks
    5 minutos -> 600 ticks
    """
    return int(match_duration_minutes * 60 / TICK_DURATION_SECONDS)


# ======================================== Pausas ==============================================

class PauseType(Enum):
    """Tipo de pausa del partido."""
    COOLING_BREAK = "COOLING_BREAK"
    HALF_TIME = "HALF_TIME"

# Duración en segundos de cada tipo de pausa.
PAUSE_DURATION_SECONDS = {
    PauseType.COOLING_BREAK: 10,
    PauseType.HALF_TIME: 20,
}

# Calendario: (porcentaje de total_ticks, tipo), en orden.
PAUSE_PLAN = (
    (25, PauseType.COOLING_BREAK),
    (50, PauseType.HALF_TIME),
    (75, PauseType.COOLING_BREAK),
)

@dataclass(frozen=True)
class PauseSlot:
    """Una pausa del calendario: su número (desde 1), el tick en que ocurre y su tipo."""
    number: int
    tick: int
    type: PauseType

def pause_schedule_for(total_ticks: int) -> list[PauseSlot]:
    """
    Calendario de pausas de un partido, en orden.

    240 ticks -> pausas en 60 (Cooling Break), 120 (Half-Time) y 180 (Cooling Break)
    600 ticks -> pausas en 150 (Cooling Break), 300 (Half-Time) y 450 (Cooling Break)

    Para cualquier otro total_ticks devuelve [] (sin pausas): solo existen
    partidos de 240 o 600 ticks.
    """
    valid_totals = {total_ticks_for(minutes) for minutes in VALID_MATCH_DURATIONS_MINUTES}
    if total_ticks not in valid_totals:
        return []

    # Se calcula proporcionalmente al total_ticks, y se redondea hacia abajo con //
    # mediante división entera.
    pause_slots = []

    for number, (percentage, pause_type) in enumerate(PAUSE_PLAN, start=1):
        tick = total_ticks * percentage // 100

        pause_slots.append(
            PauseSlot(
                number=number,
                tick=tick,
                type=pause_type,
            )
        )

    return pause_slots
