"""
Este __init__ importa todos los modelos del proyecto para que:
  1. `Base.metadata` los conozca a todos (necesario para que Alembic pueda
     autogenerar migraciones con `--autogenerate`).
  2. Las relaciones declaradas con strings (ej. relationship("Team")) puedan
     resolverse sin importar manualmente cada módulo en el punto de uso.
"""

from src.models.team import Team 
from src.models.user import User  
from src.models.behavior import Behavior, BehaviorType
from src.models.player import Player
from src.models.match import Match, MatchStatus
from src.models.lineup_entry import LineupEntry
from src.models.league import League, LeagueStatus

__all__ = ["Team", "User","Behavior","Player", "Match", "MatchStatus", "LineupEntry", "League", "LeagueStatus", "BehaviorType"]
