"""Add action proposals table for secure human approval workflow.

Revision ID: 20260830_0002
Revises: 20260829_0001
Create Date: 2026-08-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260830_0002"
down_revision: Union[str, Sequence[str], None] = "20260829_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _enum(*values: str, name: str, length: int = 32) -> sa.Enum:
    return sa.Enum(
        *values,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=length,
    )


def upgrade() -> None:
    uuid = sa.Uuid()
    timestamp = sa.DateTime(timezone=True)

    op.create_table(
        "action_proposals",
        sa.Column("id", uuid, nullable=False),
        sa.Column("incident_id", uuid, nullable=False),
        sa.Column("organization_id", uuid, nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            _enum("pending_approval", "approved", "rejected", "expired", "executed", "failed", name="action_proposal_status"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("expires_at", timestamp, nullable=False),
        sa.Column("proposed_by_actor_type", _enum("user", "system", "ai", name="audit_actor_type"), nullable=False),
        sa.Column("proposed_by_user_id", uuid, nullable=True),
        sa.Column("approved_by_user_id", uuid, nullable=True),
        sa.Column("approved_at", timestamp, nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("execution_result", sa.JSON(), nullable=True),
        sa.Column("executed_at", timestamp, nullable=True),
        sa.Column("created_at", timestamp, nullable=False),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["proposed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_action_proposals_idempotency_key"),
    )
    op.create_index("ix_action_proposals_incident_id", "action_proposals", ["incident_id"])
    op.create_index("ix_action_proposals_organization_id", "action_proposals", ["organization_id"])
    op.create_index("ix_action_proposals_status", "action_proposals", ["status"])
    op.create_index("ix_action_proposals_expires_at", "action_proposals", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_action_proposals_expires_at", table_name="action_proposals")
    op.drop_index("ix_action_proposals_status", table_name="action_proposals")
    op.drop_index("ix_action_proposals_organization_id", table_name="action_proposals")
    op.drop_index("ix_action_proposals_incident_id", table_name="action_proposals")
    op.drop_table("action_proposals")
