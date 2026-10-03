


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