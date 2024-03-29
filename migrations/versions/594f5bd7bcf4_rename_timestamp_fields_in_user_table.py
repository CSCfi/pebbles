"""rename timestamp fields in user table

Revision ID: 594f5bd7bcf4
Revises: e1f66926f70c
Create Date: 2021-09-07 09:16:59.855225

"""

# revision identifiers, used by Alembic.
revision = '594f5bd7bcf4'
down_revision = 'e1f66926f70c'

from alembic import op


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('users', 'expiry_date', new_column_name='expiry_ts')
    op.alter_column('users', 'joining_date', new_column_name='joining_ts')
    op.alter_column('users', 'last_login_date', new_column_name='last_login_ts')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('users', 'expiry_ts', new_column_name='expiry_date')
    op.alter_column('users', 'joining_ts', new_column_name='joining_date')
    op.alter_column('users', 'last_login_ts', new_column_name='last_login_date')
    # ### end Alembic commands ###
