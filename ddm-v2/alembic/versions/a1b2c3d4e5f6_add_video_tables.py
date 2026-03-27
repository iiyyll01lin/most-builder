"""add_video_tables

Revision ID: a1b2c3d4e5f6
Revises: 9ca79ab8d9f7
Create Date: 2026-03-27 10:00:00.000000

Phase 5 — Vision Engine schema changes:
- Add ``video_uploads`` table (stores workstation video metadata).
- Add nullable ``video_timestamp_start`` and ``video_timestamp_end`` columns to
  ``sop_actions`` (ground-truth wall-clock anchors written by the Vision Engine).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "9ca79ab8d9f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add video_uploads table and video timestamp columns to sop_actions."""
    op.create_table(
        "video_uploads",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("sop_version_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("stored_filename", sa.String(length=512), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("fps", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("uploaded_by", sa.String(length=64), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["sop_version_id"],
            ["sop_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_video_uploads_sop_version_id"),
        "video_uploads",
        ["sop_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_video_uploads_project_id"),
        "video_uploads",
        ["project_id"],
        unique=False,
    )

    op.add_column(
        "sop_actions",
        sa.Column("video_timestamp_start", sa.Float(), nullable=True),
    )
    op.add_column(
        "sop_actions",
        sa.Column("video_timestamp_end", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    """Remove video_uploads table and video timestamp columns from sop_actions."""
    op.drop_column("sop_actions", "video_timestamp_end")
    op.drop_column("sop_actions", "video_timestamp_start")

    op.drop_index(op.f("ix_video_uploads_project_id"), table_name="video_uploads")
    op.drop_index(op.f("ix_video_uploads_sop_version_id"), table_name="video_uploads")
    op.drop_table("video_uploads")
