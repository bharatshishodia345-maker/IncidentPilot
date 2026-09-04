"""Add knowledge records table for verified-feedback learning layer.

Revision ID: 20260830_0003
Revises: 20260830_0002
Create Date: 2026-08-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260830_0003"
down_revision: Union[str, Sequence[str], None] = "20260830_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    uuid = sa.Uuid()
    timestamp = sa.DateTime(timezone=True)

    op.create_table(
        "knowledge_records",
        sa.Column("id", uuid, nullable=False),
        sa.Column("organization_id", uuid, nullable=False),
        sa.Column("incident_id", uuid, nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("root_cause", sa.Text(), nullable=False),
        sa.Column("effective_remediation", sa.Text(), nullable=False),
        sa.Column("preventative_actions", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("validated_by_user_id", uuid, nullable=False),
        sa.Column("validated_at", timestamp, nullable=False),
        sa.Column("created_at", timestamp, nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["validated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_records_organization_id", "knowledge_records", ["organization_id"])
    op.create_index("ix_knowledge_records_incident_id", "knowledge_records", ["incident_id"])
    op.create_index("ix_knowledge_records_validated_by_user_id", "knowledge_records", ["validated_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_records_validated_by_user_id", table_name="knowledge_records")
    op.drop_index("ix_knowledge_records_incident_id", table_name="knowledge_records")
    op.drop_index("ix_knowledge_records_organization_id", table_name="knowledge_records")
    op.drop_table("knowledge_records")
