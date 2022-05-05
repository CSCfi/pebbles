"""application memory_gib

Revision ID: e96f531e867f
Revises: f8484696a67f
Create Date: 2022-05-04 04:42:54.692728

"""

# revision identifiers, used by Alembic.
revision = 'e96f531e867f'
down_revision = 'f8484696a67f'

from alembic import op
import sqlalchemy as sa


def upgrade():
    # Convert memory_limit to memory_gib in base_config in applications and templates.
    # We have M and Gi suffixes in the database, this needs to be expanded if there are other cases in data

    # Gi suffix first
    op.execute('''
      UPDATE applications
         SET base_config=base_config::jsonb || jsonb_build_object(
           'memory_gib', cast(replace(base_config::json->>'memory_limit', 'Gi', '') as numeric)
         )
       WHERE NOT base_config::jsonb ? 'memory_gib'
         AND strpos(base_config::jsonb->>'memory_limit', 'Gi') > 0
    ''')
    op.execute('''
      UPDATE application_templates
         SET base_config=base_config::jsonb || jsonb_build_object(
           'memory_gib', cast(replace(base_config::json->>'memory_limit', 'Gi', '') as numeric)
         )
       WHERE NOT base_config::jsonb ? 'memory_gib'
         AND strpos(base_config::jsonb->>'memory_limit', 'Gi') > 0
    ''')

    # then M
    op.execute('''
      UPDATE applications
         SET base_config=base_config::jsonb || jsonb_build_object(
           'memory_gib',
           trim(trailing '00' from 
             (cast(replace(base_config::json->>'memory_limit', 'M', '') as numeric)/1024.0)::text
           )::numeric
         )
       WHERE NOT base_config::jsonb ? 'memory_gib'
         AND strpos(base_config::jsonb->>'memory_limit', 'M') > 0
    ''')
    op.execute('''
      UPDATE application_templates
         SET base_config=base_config::jsonb || jsonb_build_object(
           'memory_gib',
           trim(trailing '00' from 
             (cast(replace(base_config::json->>'memory_limit', 'M', '') as numeric)/1024.0)::text
           )::numeric
         )
       WHERE NOT base_config::jsonb ? 'memory_gib'
         AND strpos(base_config::jsonb->>'memory_limit', 'M') > 0
    ''')


def downgrade():
    # drop new 'memory_gib' field from applications and templates
    op.execute('''
      UPDATE applications
         SET base_config=base_config::jsonb - 'memory_gib'
    ''')
    op.execute('''
      UPDATE application_templates
         SET base_config=base_config::jsonb - 'memory_gib'
    ''')
