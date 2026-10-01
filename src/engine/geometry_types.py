"""
Tipos de datos geométricos, cuyo propósito es 
brindar físicas al motor del juego, entre ellas:
Fuerza, Velocidad, Posición.  
"""

from dataclasses import dataclass
# Para realizar cálculos, utilizo la librería math
import math 

"""
Vector2D:
Representa una dirección, desplazamiento o velocidad.
"""

# Nota: dataclass YA inicializa la clase, no es necesario __init__
@dataclass(frozen=True)
class Vector2D:
  x: float
  y: float

  def magnitude(self) -> float:
   """
   @brief Devuelve la rapidez o fuerza del vector (su longitud/escalar).
   Útil para calcular la velocidad independientemente de su dirección
   """
   return math.hypot(self.x, self.y)

  def normalize(self) -> 'Vector2D':
   """
   @brief Devuelve un vector de magnitud 1 en la misma dirección (vector unitario).
   Útil para calcular hacia donde va un objetivo
   """
   magn = self.magnitude()
   if magn == 0:
      return Vector2D(0,0)
   
   norm = Vector2D(self.x / magn, self.y / magn)

   return norm


"""
Point2D:
Representa un punto espacial o posición fija en el plano de la cancha.
"""

@dataclass(frozen=True)
class Point2D:
   x: float
   y: float

   def distance_to(self, other: 'Point2D') -> float:
    """
    @brief Calcula la distancia hacia otro Point2D.
    @param other Point2D a calcular la distancia.
    """
    ...

   def direction_to(self, target: 'Point2D') -> Vector2D:
    """
    @brief Retorna el Vector2D de dirección que apunta hacia 'target'.
    """
    ...