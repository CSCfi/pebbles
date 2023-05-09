"""workspace membership expiry policy

Revision ID: ff844f09586e
Revises: 3777862410d1
Create Date: 2023-05-10 05:52:00.529377

"""

# revision identifiers, used by Alembic.
revision = 'ff844f09586e'
down_revision = '3777862410d1'

import sqlalchemy as sa
from alembic import op


def upgrade():
    op.add_column('workspaces', sa.Column('membership_expiry_policy', sa.Text(), nullable=True))
    membership_expiry_policy = '{"kind": "persistent"}'
    op.execute('''
      UPDATE workspaces
         SET membership_expiry_policy='%s'
       WHERE membership_expiry_policy is NULL 
    ''' % membership_expiry_policy)


def downgrade():
    op.drop_column('workspaces', 'membership_expiry_policy')
