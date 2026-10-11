"""
MACROS, Medidas, Valores Fijos
"""

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