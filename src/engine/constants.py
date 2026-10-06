"""
Constantes PROVISORIAS

Estan todas aca, en un unico lugar, para modificarlas de forma facil

Otras constantes del motor que YA existen y no se repiten aca:
  - Dimensiones de la cancha: PITCH_LENGTH / PITCH_WIDTH en pitch.py.
  - Duración de un tick: TICK_DURATION_SECONDS en timing.py.


la velocidad máxima de carrera es proporcional al atributo
  velocidad (m/s) = MAX_RUN_SPEED_METERS_PER_SECOND * SPEED / MAX_ATTRIBUTE_VALUE
Ejemplos: SPEED 100 -> 8 m/s, SPEED 50 -> 4 m/s, SPEED 20 -> 1.6 m/s
"""

MAX_RUN_SPEED_METERS_PER_SECOND = 8.0

# Valor máximo que puede tener un atributo (mismo que _ATTRIBUTE_MAX en
# player_service.py, que valida al crear el jugador).
MAX_ATTRIBUTE_VALUE = 100


def reach_distance(control: int) -> float:
    """
    Devuelve la distancia máxima de interacción (en metros/unidades) calculada dinámicamente por el servidor según el atributo CONTROL. 
    """
    # reach_distance() es una función lineal y estrictamente creciente
    # reach_distance(control) = a * control + b
    #
    #   con CONTROL 20  queremos 0.5 m de alcance
    #   con CONTROL 100 queremos 5 m de alcance
    #
    #   a = (5 - 0.5) / (100 - 20) = 4.5 / 80 = 0.05625
    #   => por cada punto de CONTROL, el alcance aumenta 0.05625 m.
    #
    # Despejando b:
    #   0.5 = 0.05625 * 20 + b
    #   b = 0.5 - 1.125 = -0.625
    #
    # Por lo tanto:
    # reach_distance(control) = 0.05625 * control - 0.625
            
    return 0.05625 * control - 0.625

# --- Patada (kick_ball) ---
# PROVISORIO: la fórmula f(POWER, power_percentage) del ticket no está
# definida todavía. Mientras tanto la rapidez de la pelota es lineal:
#   rapidez (m/s) = MAX_KICK_SPEED_METERS_PER_SECOND * POWER / MAX_ATTRIBUTE_VALUE * power_percentage
# Ejemplos: POWER 100 a fondo -> 30 m/s, POWER 50 a fondo -> 15 m/s,
#           POWER 50 con power_percentage 0.5 -> 7.5 m/s
MAX_KICK_SPEED_METERS_PER_SECOND = 30.0


def kick_speed(power: int, power_percentage: float) -> float:
    """Rapidez (m/s) que un jugador le da a la pelota. Proporcional a power_percentage."""
    return MAX_KICK_SPEED_METERS_PER_SECOND * power / MAX_ATTRIBUTE_VALUE * power_percentage
