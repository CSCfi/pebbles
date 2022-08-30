"""alert history

Revision ID: e5ec28975cca
Revises: d0dd70559107
Create Date: 2022-07-06 13:35:53.005479

"""

# revision identifiers, used by Alembic.
revision = 'e5ec28975cca'
down_revision = 'd0dd70559107'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    # new and old contents are not compatible, old schema cannot have history
    op.drop_table('alerts')
    op.create_table('alerts',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('target', sa.String(length=64), nullable=False),
    sa.Column('source', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=64), nullable=False),
    sa.Column('first_seen_ts', sa.DateTime(), nullable=True),
    sa.Column('last_seen_ts', sa.DateTime(), nullable=True),
    sa.Column('data', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_alerts'))
    )
    op.create_index(op.f('ix_alerts_status'), 'alerts', ['status'], unique=False)


def downgrade():
    # new and old contents are not compatible, old schema cannot have history
    op.drop_table('alerts')
    op.create_table('alerts',
    sa.Column('target', sa.String(length=64), nullable=False),
    sa.Column('source', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=64), nullable=False),
    sa.Column('data', sa.Text(), nullable=True),
    sa.Column('update_ts', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('target', 'source', name=op.f('pk_alerts'))
    )
