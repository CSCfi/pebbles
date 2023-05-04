"""workspace_user_associations to workspace_memberships

Revision ID: 3777862410d1
Revises: c55e90324542
Create Date: 2023-05-04 08:52:43.505673

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = '3777862410d1'
down_revision = 'a062e7649f57'


def upgrade():
    # workspace_user_associations -> workspace_memberships
    op.rename_table('workspace_user_associations', 'workspace_memberships')
    op.execute(
        "ALTER INDEX pk_workspace_user_associations RENAME TO pk_workspace_memberships"
    )
    op.execute(
        "ALTER TABLE workspace_memberships"
        " RENAME CONSTRAINT fk_workspace_user_associations_user_id_users"
        " TO fk_workspace_memberships_user_id_users"
    )
    op.execute(
        "ALTER TABLE workspace_memberships"
        " RENAME CONSTRAINT fk_workspace_user_associations_workspace_id_workspaces"
        " TO fk_workspace_memberships_workspace_id_workspaces"
    )


def downgrade():
    #  workspace_memberships -> workspace_user_associations
    op.execute(
        "ALTER TABLE workspace_memberships"
        " RENAME CONSTRAINT fk_workspace_memberships_workspace_id_workspaces"
        " TO fk_workspace_user_associations_workspace_id_workspaces"
    )
    op.execute(
        "ALTER TABLE workspace_memberships"
        " RENAME CONSTRAINT fk_workspace_memberships_user_id_users"
        " TO fk_workspace_user_associations_user_id_users"
    )
    op.execute(
        "ALTER INDEX pk_workspace_memberships RENAME TO pk_workspace_user_associations"
    )
    op.rename_table('workspace_memberships', 'workspace_user_associations')
