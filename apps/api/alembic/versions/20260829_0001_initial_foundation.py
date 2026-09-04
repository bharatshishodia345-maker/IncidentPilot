"""Initial IncidentPilot MVP foundation.

Revision ID: 20260829_0001
Revises:
Create Date: 2026-08-29
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260829_0001"
down_revision: Union[str, Sequence[str], None] = None
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
        "organizations",
        sa.Column("id", uuid, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", timestamp, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "users",
        sa.Column("id", uuid, nullable=False),
        sa.Column("organization_id", uuid, nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column(
            "role",
            _enum("incident_commander", "responder", "observer", name="user_role"),
            nullable=False,
        ),
        sa.Column("created_at", timestamp, nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "subject", name="uq_users_organization_subject"),
    )
    op.create_index("ix_users_organization_id", "users", ["organization_id"])

    op.create_table(
        "incidents",
        sa.Column("id", uuid, nullable=False),
        sa.Column("organization_id", uuid, nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column(
            "status",
            _enum("declared", "open", "mitigated", "resolved", name="incident_status"),
            nullable=False,
        ),
        sa.Column("severity", _enum("sev1", "sev2", "sev3", "sev4", name="incident_severity"), nullable=False),
        sa.Column("commander_user_id", uuid, nullable=False),
        sa.Column("opened_at", timestamp, nullable=False),
        sa.Column("closed_at", timestamp, nullable=True),
        sa.Column("created_at", timestamp, nullable=False),
        sa.Column("updated_at", timestamp, nullable=False),
        sa.ForeignKeyConstraint(["commander_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incidents_organization_id", "incidents", ["organization_id"])
    op.create_index("ix_incidents_status", "incidents", ["status"])

    op.create_table(
        "incident_participants",
        sa.Column("id", uuid, nullable=False),
        sa.Column("incident_id", uuid, nullable=False),
        sa.Column("user_id", uuid, nullable=False),
        sa.Column("presence_state", _enum("joined", "left", name="presence_state"), nullable=False),
        sa.Column("joined_at", timestamp, nullable=False),
        sa.Column("left_at", timestamp, nullable=True),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("incident_id", "user_id", name="uq_incident_participant"),
    )
    op.create_index("ix_incident_participants_incident_id", "incident_participants", ["incident_id"])
    op.create_index("ix_incident_participants_user_id", "incident_participants", ["user_id"])

    op.create_table(
        "action_items",
        sa.Column("id", uuid, nullable=False),
        sa.Column("incident_id", uuid, nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_user_id", uuid, nullable=True),
        sa.Column(
            "status",
            _enum("open", "in_progress", "blocked", "done", name="action_status"),
            nullable=False,
        ),
        sa.Column("due_at", timestamp, nullable=True),
        sa.Column("created_at", timestamp, nullable=False),
        sa.Column("updated_at", timestamp, nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_action_items_incident_id", "action_items", ["incident_id"])
    op.create_index("ix_action_items_owner_user_id", "action_items", ["owner_user_id"])
    op.create_index("ix_action_items_status", "action_items", ["status"])

    op.create_table(
        "timeline_events",
        sa.Column("id", uuid, nullable=False),
        sa.Column("incident_id", uuid, nullable=False),
        sa.Column(
            "event_type",
            _enum("observation", "decision", "action", "status_change", "note", name="timeline_event_type"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("occurred_at", timestamp, nullable=False),
        sa.Column("created_by_user_id", uuid, nullable=True),
        sa.Column("created_at", timestamp, nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_timeline_events_incident_id", "timeline_events", ["incident_id"])
    op.create_index("ix_timeline_events_event_type", "timeline_events", ["event_type"])
    op.create_index("ix_timeline_events_occurred_at", "timeline_events", ["occurred_at"])

    op.create_table(
        "audit_events",
        sa.Column("id", uuid, nullable=False),
        sa.Column("organization_id", uuid, nullable=False),
        sa.Column("incident_id", uuid, nullable=True),
        sa.Column("actor_type", _enum("user", "system", "ai", name="audit_actor_type"), nullable=False),
        sa.Column("actor_user_id", uuid, nullable=True),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", timestamp, nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_actor_user_id", "audit_events", ["actor_user_id"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_incident_id", "audit_events", ["incident_id"])
    op.create_index("ix_audit_events_occurred_at", "audit_events", ["occurred_at"])
    op.create_index("ix_audit_events_organization_id", "audit_events", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_organization_id", table_name="audit_events")
    op.drop_index("ix_audit_events_occurred_at", table_name="audit_events")
    op.drop_index("ix_audit_events_incident_id", table_name="audit_events")
    op.drop_index("ix_audit_events_event_type", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_user_id", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index("ix_timeline_events_occurred_at", table_name="timeline_events")
    op.drop_index("ix_timeline_events_event_type", table_name="timeline_events")
    op.drop_index("ix_timeline_events_incident_id", table_name="timeline_events")
    op.drop_table("timeline_events")

    op.drop_index("ix_action_items_status", table_name="action_items")
    op.drop_index("ix_action_items_owner_user_id", table_name="action_items")
    op.drop_index("ix_action_items_incident_id", table_name="action_items")
    op.drop_table("action_items")

    op.drop_index("ix_incident_participants_user_id", table_name="incident_participants")
    op.drop_index("ix_incident_participants_incident_id", table_name="incident_participants")
    op.drop_table("incident_participants")

    op.drop_index("ix_incidents_status", table_name="incidents")
    op.drop_index("ix_incidents_organization_id", table_name="incidents")
    op.drop_table("incidents")

    op.drop_index("ix_users_organization_id", table_name="users")
    op.drop_table("users")
    op.drop_table("organizations")

