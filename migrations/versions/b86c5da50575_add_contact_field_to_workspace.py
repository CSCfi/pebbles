"""add contact field to workspace

Revision ID: b86c5da50575
Revises: c702dff56bb0
Create Date: 2023-12-06 18:06:31.963865

"""

# revision identifiers, used by Alembic.
revision = 'b86c5da50575'
down_revision = 'c702dff56bb0'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('workspaces', sa.Column('contact', sa.Text))


def downgrade():
    op.drop_column('workspaces', 'contact')

