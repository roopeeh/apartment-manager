"""Initial migration

Revision ID: 001
Revises:
Create Date: 2026-03-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create app_role enum idempotently
    op.execute(sa.text(
        "DO $$ BEGIN "
        "CREATE TYPE app_role AS ENUM ('super_admin', 'admin', 'resident'); "
        "EXCEPTION WHEN duplicate_object THEN null; "
        "END $$;"
    ))

    # societies
    op.create_table(
        "societies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.Text, nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(20)),
        sa.Column("email", sa.String(255)),
        sa.Column("logo_url", sa.Text),
        sa.Column("total_blocks", sa.Integer, server_default="0"),
        sa.Column("blocks", postgresql.JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("floors", postgresql.JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("config", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("payment_gateway", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("plan", sa.String(20), server_default="'basic'"),
        sa.Column("status", sa.String(20), server_default="'onboarding'"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(20)),
        sa.Column("avatar_url", sa.Text),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("reset_token", sa.String(255)),
        sa.Column("reset_token_expires", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # user_roles
    op.create_table(
        "user_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("society_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("societies.id", ondelete="CASCADE"), nullable=True),
        sa.Column("role", postgresql.ENUM(name="app_role", create_type=False), nullable=False),
        sa.UniqueConstraint("user_id", "society_id", "role", name="uq_user_society_role"),
    )

    # refresh_tokens
    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(255), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # flats
    op.create_table(
        "flats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("society_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("societies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("flat_number", sa.String(20), nullable=False),
        sa.Column("block", sa.String(10), nullable=False),
        sa.Column("floor", sa.Integer, nullable=False),
        sa.Column("area", sa.Integer),
        sa.Column("owner_name", sa.String(255)),
        sa.Column("phone", sa.String(20)),
        sa.Column("email", sa.String(255)),
        sa.Column("occupancy", sa.String(10), server_default="'vacant'"),
        sa.Column("maintenance_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("society_id", "flat_number", name="uq_society_flat_number"),
    )

    # residents
    op.create_table(
        "residents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("society_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("societies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("flat_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("flats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(20)),
        sa.Column("email", sa.String(255)),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("active", sa.Boolean, server_default="true"),
        sa.Column("move_in_date", sa.Date),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # payments
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("society_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("societies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("flat_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("flats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("month", sa.String(3), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("maintenance_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("amount_paid", sa.Numeric(10, 2), server_default="0"),
        sa.Column("status", sa.String(10), server_default="'unpaid'"),
        sa.Column("payment_date", sa.Date),
        sa.Column("payment_mode", sa.String(50)),
        sa.Column("transaction_ref", sa.String(100)),
        sa.Column("gateway_order_id", sa.String(100)),
        sa.Column("remarks", sa.Text, server_default="''"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("society_id", "flat_id", "month", "year", name="uq_payment_flat_month_year"),
    )

    # expenses
    op.create_table(
        "expenses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("society_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("societies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("vendor", sa.String(255)),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("added_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("notes", sa.Text, server_default="''"),
        sa.Column("attachment_url", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # notices
    op.create_table(
        "notices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("society_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("societies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("priority", sa.String(10), server_default="'medium'"),
        sa.Column("pinned", sa.Boolean, server_default="false"),
        sa.Column("posted_by", sa.String(255)),
        sa.Column("posted_date", sa.Date, server_default=sa.text("CURRENT_DATE")),
        sa.Column("expiry_date", sa.Date),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Indexes
    op.create_index("idx_flats_society", "flats", ["society_id"])
    op.create_index("idx_residents_society", "residents", ["society_id"])
    op.create_index("idx_residents_flat", "residents", ["flat_id"])
    op.create_index("idx_payments_society_month", "payments", ["society_id", "month", "year"])
    op.create_index("idx_payments_flat", "payments", ["flat_id"])
    op.create_index("idx_payments_status", "payments", ["society_id", "status"])
    op.create_index("idx_expenses_society_date", "expenses", ["society_id", "date"])
    op.create_index("idx_expenses_category", "expenses", ["society_id", "category"])
    op.create_index("idx_notices_society", "notices", ["society_id"])
    op.create_index("idx_user_roles_user", "user_roles", ["user_id"])
    op.create_index("idx_user_roles_society", "user_roles", ["society_id"])


def downgrade() -> None:
    op.drop_table("notices")
    op.drop_table("expenses")
    op.drop_table("payments")
    op.drop_table("residents")
    op.drop_table("flats")
    op.drop_table("refresh_tokens")
    op.drop_table("user_roles")
    op.drop_table("users")
    op.drop_table("societies")

    op.execute("DROP TYPE IF EXISTS app_role")
