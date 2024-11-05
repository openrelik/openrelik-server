"""Rename Group column

Revision ID: b7d67e6bb29e
Revises: 75458b35f1b5
Create Date: 2024-11-03 16:53:15.555911

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7d67e6bb29e"
down_revision: Union[str, None] = "75458b35f1b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "group",
        "display_name",
        new_column_name="name",
        existing_type=sa.UnicodeText(),
        nullable=False,
    )
    op.alter_column("group", "description", existing_type=sa.TEXT(), nullable=True)
    op.drop_index("ix_group_display_name", table_name="group")
    op.create_index(op.f("ix_group_name"), "group", ["name"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_group_name"), table_name="group")
    op.create_index("ix_group_display_name", "group", ["display_name"], unique=False)
    op.alter_column("group", "description", existing_type=sa.TEXT(), nullable=False)
    op.alter_column(
        "group",
        "name",
        new_column_name="display_name",
        existing_type=sa.UnicodeText(),
        nullable=False,
    )
