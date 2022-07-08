"""add tasks

Revision ID: d6163d3432c1
Revises: 33431e7c6011
Create Date: 2022-07-08 06:23:54.127876

"""

# revision identifiers, used by Alembic.
revision = 'd6163d3432c1'
down_revision = '33431e7c6011'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.create_table('tasks',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('state', sa.String(length=32), nullable=True),
    sa.Column('data', sa.Text(), nullable=True),
    sa.Column('create_ts', sa.DateTime(), nullable=True),
    sa.Column('complete_ts', sa.DateTime(), nullable=True),
    sa.Column('update_ts', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id', 'kind', name=op.f('pk_tasks'))
    )


def downgrade():
    op.drop_table('tasks')
