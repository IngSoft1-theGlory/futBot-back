"""
Este __init__ importa todos los modelos del proyecto para que:
  1. `Base.metadata` los conozca a todos (necesario para que Alembic pueda
     autogenerar migraciones con `--autogenerate`).
  2. Las relaciones declaradas con strings (ej. relationship("Team")) puedan
     resolverse sin importar manualmente cada módulo en el punto de uso.

Cuando se implemente el modelo completo de Team (y luego Player, Behavior,
League, Match, etc.), cada nuevo módulo de modelo debe agregarse acá.
"""

from src.models.team import Team 
from src.models.user import User  
from src.models.behavior import Behavior
from src.models.player import Player
from src.models.match import Match, MatchStatus

__all__ = ["Team", "User","Behavior","Player", "Match", "MatchStatus"]
