"""rename environment to application

Revision ID: 2db948e18094
Revises: 63e1cbb91610
Create Date: 2021-11-10 16:19:08.636464

"""

# revision identifiers, used by Alembic.
revision = '2db948e18094'
down_revision = '63e1cbb91610'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.rename_table('environment_templates', 'application_templates')
    op.alter_column('application_templates', 'environment_type', new_column_name='application_type')

    op.rename_table('environment_sessions', 'application_sessions')
    op.alter_column('application_sessions', 'environment_id', new_column_name='application_id')
    op.create_unique_constraint(op.f('uq_application_sessions_name'), 'application_sessions', ['name'])
    op.drop_constraint('uq_environment_sessions_name', 'application_sessions', type_='unique')

    op.rename_table('environment_session_logs', 'application_session_logs')
    op.alter_column('application_session_logs', 'environment_session_id', new_column_name='application_session_id')
    op.create_index(op.f('ix_application_session_logs_application_session_id'), 'application_session_logs', ['application_session_id'], unique=False)
    op.drop_index('ix_environment_session_logs_environment_session_id', table_name='application_session_logs')

    op.rename_table('environments', 'applications')

    op.alter_column('workspaces', 'environment_quota', new_column_name='application_quota')


def downgrade():
    op.alter_column('workspaces', 'application_quota', new_column_name='environment_quota')

    op.rename_table('application_templates', 'environment_templates')
    op.alter_column('environment_templates', 'application_type', new_column_name='environment_type')

    op.create_unique_constraint('uq_environment_sessions_name', 'application_sessions', ['name'])
    op.drop_constraint(op.f('uq_application_sessions_name'), 'application_sessions', type_='unique')
    op.rename_table('application_sessions', 'environment_sessions')
    op.alter_column('environment_sessions', 'application_id', new_column_name='environment_id')

    op.create_index('ix_environment_session_logs_environment_session_id', 'application_session_logs', ['application_session_id'], unique=False)
    op.drop_index(op.f('ix_application_session_logs_application_session_id'), table_name='application_session_logs')
    op.rename_table('application_session_logs', 'environment_session_logs')
    op.alter_column('environment_session_logs', 'application_session_id', new_column_name='environment_session_id')

    op.rename_table('applications', 'environments')
