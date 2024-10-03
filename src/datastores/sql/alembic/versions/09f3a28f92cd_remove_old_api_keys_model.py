"""Remove old API keys model

Revision ID: 09f3a28f92cd
Revises: 0d0800088b4a
Create Date: 2024-09-28 11:32:39.324173

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '09f3a28f92cd'
down_revision: Union[str, None] = '0d0800088b4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('ix_userapikey_display_name', table_name='userapikey')
    op.drop_table('userapikey')
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('userapikey',
    sa.Column('display_name', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('description', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('api_key', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('access_token', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('expires_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('user_id', sa.BIGINT(), autoincrement=False, nullable=False),
    sa.Column('id', sa.BIGINT(), autoincrement=True, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('deleted_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('is_deleted', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], name='userapikey_user_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='userapikey_pkey')
    )
    op.create_index('ix_userapikey_display_name', 'userapikey', ['display_name'], unique=False)
    # ### end Alembic commands ###