"""
Importa todos los modelos para que Base.metadata los conozca (necesario
para Alembic --autogenerate) y para que las relationship("...") por string
se resuelvan sin importar manualmente cada módulo.
"""

from src.models.team import Team 
from src.models.user import User 

__all__ = ["Team", "User"]