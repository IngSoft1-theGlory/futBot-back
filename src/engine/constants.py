"""
Constantes PROVISORIAS

Estan todas aca, en un unico lugar, para modificarlas de forma facil

Otras constantes del motor que YA existen y no se repiten aca:
  - Dimensiones de la cancha: PITCH_LENGTH / PITCH_WIDTH en pitch.py.
  - Duración de un tick: TICK_DURATION_SECONDS en timing.py.
"""

# [PREGUNTA ABIERTA] Formula de SPEED.
# Propuesta: la velocidad máxima de carrera es proporcional al atributo
#   velocidad (m/s) = MAX_RUN_SPEED_METERS_PER_SECOND * SPEED / MAX_ATTRIBUTE_VALUE
# Ejemplos: SPEED 100 -> 8 m/s, SPEED 50 -> 4 m/s, SPEED 20 -> 1.6 m/s.
MAX_RUN_SPEED_METERS_PER_SECOND = 8.0

# Valor máximo que puede tener un atributo (mismo que _ATTRIBUTE_MAX en
# player_service.py, que valida al crear el jugador).
MAX_ATTRIBUTE_VALUE = 100
