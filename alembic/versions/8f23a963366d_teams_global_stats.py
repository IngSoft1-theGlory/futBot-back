"""
teams global stats

Revision ID: 8f23a963366d
Revises: 969ca3575aaa
Create Date: 2026-11-08 14:39:54.305863

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f23a963366d'
down_revision: Union[str, Sequence[str], None] = '969ca3575aaa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Estadisticas globales de cada club (ranking global).
    # server_default='0': los equipos que ya existen quedan con todo en 0 al migrar
    op.add_column('teams', sa.Column('matches_played', sa.Integer(), server_default='0', nullable=False))
    op.add_column('teams', sa.Column('wins', sa.Integer(), server_default='0', nullable=False))
    op.add_column('teams', sa.Column('draws', sa.Integer(), server_default='0', nullable=False))
    op.add_column('teams', sa.Column('losses', sa.Integer(), server_default='0', nullable=False))
    op.add_column('teams', sa.Column('goals_for', sa.Integer(), server_default='0', nullable=False))
    op.add_column('teams', sa.Column('goals_against', sa.Integer(), server_default='0', nullable=False))
    op.add_column('teams', sa.Column('points', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('teams', 'points')
    op.drop_column('teams', 'goals_against')
    op.drop_column('teams', 'goals_for')
    op.drop_column('teams', 'losses')
    op.drop_column('teams', 'draws')
    op.drop_column('teams', 'wins')
    op.drop_column('teams', 'matches_played')
