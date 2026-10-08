"""ligas: tabla leagues, league_id en matches y lineup_entries

Revision ID: 6d7fd6975215
Revises: 136eaad6651a
Create Date: 2026-10-08 01:59:27.396364

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6d7fd6975215'
down_revision: Union[str, Sequence[str], None] = '136eaad6651a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('leagues',
    sa.Column('league_id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('league_name', sa.Text(), nullable=False),
    sa.Column('max_teams', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'IN_PROGRESS', 'FINISHED', name='status_valid', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=True),
    sa.Column('match_duration', sa.Integer(), nullable=False),
    sa.Column('host_team_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('match_duration > 0', name=op.f('ck_leagues_duration_positive')),
    sa.CheckConstraint('max_teams IN (4, 6, 8, 10, 12)', name=op.f('ck_leagues_capacity_valid')),
    sa.ForeignKeyConstraint(['host_team_id'], ['teams.team_id'], name=op.f('fk_leagues_host_team_id_teams'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('league_id', name=op.f('pk_leagues'))
    )
    op.create_index(op.f('ix_leagues_host_team_id'), 'leagues', ['host_team_id'], unique=False)
    op.create_index(op.f('ix_leagues_status'), 'leagues', ['status'], unique=False)

    # batch_alter_table: SQLite no soporta ALTER COLUMN ni ADD CONSTRAINT, asi que
    # Alembic recrea la tabla. En Postgres emite los ALTER normales.
    with op.batch_alter_table('lineup_entries') as batch_op:
        batch_op.add_column(sa.Column('league_id', sa.Integer(), nullable=True))
        batch_op.alter_column('match_id', existing_type=sa.INTEGER(), nullable=True)
        batch_op.create_unique_constraint('uq_lineup_entries_league_player', ['league_id', 'player_id'])
        batch_op.create_unique_constraint('uq_lineup_entries_league_team_role', ['league_id', 'team_id', 'role'])
        batch_op.create_foreign_key(op.f('fk_lineup_entries_league_id_leagues'), 'leagues', ['league_id'], ['league_id'], ondelete='CASCADE')
        # Alembic no detecta CHECK nuevos sobre tablas existentes: se agrega a mano
        batch_op.create_check_constraint(
            op.f("ck_lineup_entries_either_match_id_or_league_id_for_lineup"),
            "(match_id IS NULL AND league_id IS NOT NULL) OR (league_id IS NULL AND match_id IS NOT NULL)",
        )

    with op.batch_alter_table('matches') as batch_op:
        batch_op.add_column(sa.Column('league_id', sa.Integer(), nullable=True))
        batch_op.create_index(op.f('ix_matches_league_id'), ['league_id'], unique=False)
        batch_op.create_foreign_key(op.f('fk_matches_league_id_leagues'), 'leagues', ['league_id'], ['league_id'], ondelete='CASCADE')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('matches') as batch_op:
        batch_op.drop_constraint(op.f('fk_matches_league_id_leagues'), type_='foreignkey')
        batch_op.drop_index(op.f('ix_matches_league_id'))
        batch_op.drop_column('league_id')

    with op.batch_alter_table('lineup_entries') as batch_op:
        batch_op.drop_constraint(op.f("ck_lineup_entries_either_match_id_or_league_id_for_lineup"), type_="check")
        batch_op.drop_constraint(op.f('fk_lineup_entries_league_id_leagues'), type_='foreignkey')
        batch_op.drop_constraint('uq_lineup_entries_league_team_role', type_='unique')
        batch_op.drop_constraint('uq_lineup_entries_league_player', type_='unique')
        batch_op.alter_column('match_id', existing_type=sa.INTEGER(), nullable=False)
        batch_op.drop_column('league_id')

    op.drop_index(op.f('ix_leagues_status'), table_name='leagues')
    op.drop_index(op.f('ix_leagues_host_team_id'), table_name='leagues')
    op.drop_table('leagues')