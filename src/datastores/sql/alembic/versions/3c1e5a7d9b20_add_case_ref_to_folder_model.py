"""Add case reference to Folder model

Revision ID: 3c1e5a7d9b20
Revises: 49974ebaed96
Create Date: 2026-10-29 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3c1e5a7d9b20"
down_revision: Union[str, None] = "49974ebaed96"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("folder", sa.Column("case_ref", sa.Unicode(length=255), nullable=True))
    # At most one folder per case. NULLs don't conflict, so existing folders are fine. Deleted
    # folders keep their reference, but don't hold it. Like the earlier migrations, this one is
    # for Postgres only.
    op.create_index(
        "ix_folder_case_ref",
        "folder",
        ["case_ref"],
        unique=True,
        postgresql_where=sa.text("NOT is_deleted"),
    )
    op.create_check_constraint(
        "ck_folder_case_ref_root", "folder", "case_ref IS NULL OR parent_id IS NULL"
    )


def downgrade() -> None:
    op.drop_constraint("ck_folder_case_ref_root", "folder", type_="check")
    op.drop_index("ix_folder_case_ref", table_name="folder")
    op.drop_column("folder", "case_ref")
