"""Add ExternalStorage model and external file fields

Revision ID: e3f1a2b4c5d6
Revises: 49974ebaed96
Create Date: 2026-04-14 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3f1a2b4c5d6"
down_revision: Union[str, None] = "49974ebaed96"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the externalstorage table.
    op.create_table(
        "externalstorage",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer, "sqlite"),
            primary_key=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_purged",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("name", sa.UnicodeText(), nullable=False),
        sa.Column("mount_point", sa.UnicodeText(), nullable=False),
        sa.Column("description", sa.UnicodeText(), nullable=True),
    )
    op.create_index(
        op.f("ix_externalstorage_name"), "externalstorage", ["name"], unique=True
    )

    # Add external storage columns to the file table.
    op.add_column(
        "file",
        sa.Column("external_storage_name", sa.UnicodeText(), nullable=True),
    )
    op.add_column(
        "file",
        sa.Column("external_relative_path", sa.UnicodeText(), nullable=True),
    )
    op.create_index(
        op.f("ix_file_external_storage_name"),
        "file",
        ["external_storage_name"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_file_external_storage_name",
        "file",
        "externalstorage",
        ["external_storage_name"],
        ["name"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_file_external_storage_name", "file", type_="foreignkey")
    op.drop_index(op.f("ix_file_external_storage_name"), table_name="file")
    op.drop_column("file", "external_relative_path")
    op.drop_column("file", "external_storage_name")

    op.drop_index(op.f("ix_externalstorage_name"), table_name="externalstorage")
    op.drop_table("externalstorage")
