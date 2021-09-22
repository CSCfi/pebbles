"""rename instance to environment_session

Revision ID: 63e1cbb91610
Revises: da41c0a6e015
Create Date: 2021-09-22 05:28:44.257679

"""

# revision identifiers, used by Alembic.
revision = '63e1cbb91610'
down_revision = 'da41c0a6e015'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade():
    # instances -> environment_sessions
    op.rename_table('instances', 'environment_sessions')
    op.alter_column('environment_sessions', 'instance_data', new_column_name='session_data')
    op.execute('ALTER INDEX pk_instances RENAME TO pk_environment_sessions')
    op.execute('ALTER INDEX uq_instances_name RENAME TO uq_environment_sessions_name')
    op.execute(
        'ALTER TABLE environment_sessions RENAME CONSTRAINT fk_instances_environment_id_environments TO fk_environment_sessions_environment_id_environments')
    op.execute(
        'ALTER TABLE environment_sessions RENAME CONSTRAINT fk_instances_user_id_users TO fk_environment_sessions_user_id_users')

    # instance_logs -> environment_session_logs
    op.rename_table('instance_logs', 'environment_session_logs')
    op.alter_column('environment_session_logs', 'instance_id', new_column_name='environment_session_id')
    op.execute('ALTER INDEX pk_instance_logs RENAME TO pk_environment_session_logs')
    op.execute('ALTER INDEX ix_instance_logs_instance_id RENAME TO ix_environment_session_logs_environment_session_id')
    op.execute(
        'ALTER TABLE environment_session_logs RENAME CONSTRAINT fk_instance_logs_instance_id_instances TO fk_environment_session_logs_environment_session_id_environment_sessions')

    # update templates to use session_id instead of instance_id
    op.execute(
        "UPDATE environment_templates SET base_config = REPLACE(base_config, '{{instance_id}}', '{{session_id}}')")


def downgrade():
    # environment_sessions -> instances
    op.rename_table('environment_sessions', 'instances')
    op.alter_column('instances', 'session_data', new_column_name='instance_data')
    op.execute('ALTER INDEX pk_environment_sessions RENAME TO pk_instances')
    op.execute('ALTER INDEX uq_environment_sessions_name RENAME TO uq_instances_name')
    op.execute(
        'ALTER TABLE instances RENAME CONSTRAINT fk_environment_sessions_environment_id_environments TO fk_instances_environment_id_environments')
    op.execute(
        'ALTER TABLE instances RENAME CONSTRAINT fk_environment_sessions_user_id_users TO fk_instances_user_id_users')

    # instance_logs -> environment_session_logs
    op.rename_table('environment_session_logs', 'instance_logs')
    op.alter_column('instance_logs', 'environment_session_id', new_column_name='instance_id')
    op.execute('ALTER INDEX pk_environment_session_logs RENAME TO pk_instance_logs')
    op.execute('ALTER INDEX ix_environment_session_logs_environment_session_id RENAME TO ix_instance_logs_instance_id')
    op.execute(
        'ALTER TABLE instance_logs RENAME CONSTRAINT fk_environment_session_logs_environment_session_id_environment_sessions TO fk_instance_logs_instance_id_instances')

    # revert templates to use instance_id instead of session_id
    op.execute(
        "UPDATE environment_templates SET base_config = REPLACE(base_config, '{{session_id}}' , '{{instance_id}}')")
