"""Tasks should have a field for results

Revision ID: a062e7649f57
Revises: c55e90324542
Create Date: 2023-05-10 22:18:24.611093

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a062e7649f57'
down_revision = 'c55e90324542'


def upgrade():
    op.add_column('tasks', sa.Column('results', sa.Text))


def downgrade():
    op.drop_column('tasks', 'results')
