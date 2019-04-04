"""empty message

Revision ID: 37s5rj356547
Revises: j4d9g3scvf4s
Create Date: 2019-02-20 16:45:34.186981

"""

# revision identifiers, used by Alembic.
revision = '37s5rj356547'
down_revision = 'j4d9g3scvf4s'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column('users', sa.Column('group_quota', sa.Float(), nullable=True))
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('users', 'group_quota')
    ### end Alembic commands ###