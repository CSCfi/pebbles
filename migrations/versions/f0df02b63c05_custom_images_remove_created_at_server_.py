"""custom images remove created_at server default

Revision ID: f0df02b63c05
Revises: 947e2b4aa58f
Create Date: 2025-01-22 10:07:29.622289

"""

# revision identifiers, used by Alembic.
revision = 'f0df02b63c05'
down_revision = '947e2b4aa58f'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.alter_column('custom_images', 'created_at', server_default=None)

def downgrade():
    op.alter_column('custom_images', 'created_at', server_default=sa.text('now()'))
