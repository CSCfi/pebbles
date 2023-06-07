"""user annotations

Revision ID: 998437d5ea7a
Revises: ff844f09586e
Create Date: 2023-06-07 12:19:14.120934

"""

# revision identifiers, used by Alembic.
revision = '998437d5ea7a'
down_revision = 'ff844f09586e'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('users', sa.Column('annotations', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('users', 'annotations')
