"""Add external mount fields to folder model

Revision ID: b20df176dd1b
Revises: e3f1a2b4c5d6
Create Date: 2026-04-15 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b20df176dd1b"
down_revision: Union[str, None] = "e3f1a2b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add external mount columns to the folder table
    op.add_column("folder", sa.Column("external_storage_name", sa.UnicodeText(), nullable=True))
    op.add_column("folder", sa.Column("external_base_path", sa.UnicodeText(), nullable=True))
    op.create_index(
        op.f("ix_folder_external_storage_name"),
        "folder",
        ["external_storage_name"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_folder_external_storage_name",
        "folder",
        "externalstorage",
        ["external_storage_name"],
        ["name"],
    )
    # Remove duplicate external file rows before adding the unique constraint,
    # keeping only the row with the highest id for each
    # (folder_id, external_storage_name, external_relative_path) combination.
    # Rows where any of the three columns is NULL are not duplicates by definition
    # (NULL != NULL), so we filter them out of the dedup query.
    # Related userrole rows must be deleted first to satisfy the FK constraint.
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            WITH dup_ids AS (
                SELECT id
                FROM file
                WHERE folder_id IS NOT NULL
                  AND external_storage_name IS NOT NULL
                  AND external_relative_path IS NOT NULL
                  AND id NOT IN (
                      SELECT MAX(id)
                      FROM file
                      WHERE folder_id IS NOT NULL
                        AND external_storage_name IS NOT NULL
                        AND external_relative_path IS NOT NULL
                      GROUP BY folder_id, external_storage_name, external_relative_path
                  )
            )
            DELETE FROM userrole WHERE file_id IN (SELECT id FROM dup_ids)
            """
        )
    )
    conn.execute(
        sa.text(
            """
            WITH dup_ids AS (
                SELECT id
                FROM file
                WHERE folder_id IS NOT NULL
                  AND external_storage_name IS NOT NULL
                  AND external_relative_path IS NOT NULL
                  AND id NOT IN (
                      SELECT MAX(id)
                      FROM file
                      WHERE folder_id IS NOT NULL
                        AND external_storage_name IS NOT NULL
                        AND external_relative_path IS NOT NULL
                      GROUP BY folder_id, external_storage_name, external_relative_path
                  )
            )
            DELETE FROM file WHERE id IN (SELECT id FROM dup_ids)
            """
        )
    )

    # Unique constraint on file table to prevent duplicate lazy registrations.
    # NULL != NULL in PostgreSQL unique constraints, so regular files (where these
    # columns are NULL) are unaffected — only external file rows are constrained.
    op.create_unique_constraint(
        "uq_file_folder_external",
        "file",
        ["folder_id", "external_storage_name", "external_relative_path"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_file_folder_external", "file", type_="unique")
    op.drop_constraint("fk_folder_external_storage_name", "folder", type_="foreignkey")
    op.drop_index(op.f("ix_folder_external_storage_name"), table_name="folder")
    op.drop_column("folder", "external_base_path")
    op.drop_column("folder", "external_storage_name")
