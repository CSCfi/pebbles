"""workspace membership join policy

Revision ID: c702dff56bb0
Revises: 998437d5ea7a
Create Date: 2023-06-08 09:39:09.650645

"""

# revision identifiers, used by Alembic.
revision = 'c702dff56bb0'
down_revision = '998437d5ea7a'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('workspaces', sa.Column('membership_join_policy', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('workspaces', 'membership_join_policy')
