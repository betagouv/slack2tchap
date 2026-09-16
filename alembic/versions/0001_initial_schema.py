"""Initial database schema with users, matrix_accounts, webhooks and admin seeding.

Revision ID: 0001
Revises: None
Create Date: 2026-09-15 17:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("api_key_hash", sa.String(length=64), nullable=False),
        sa.Column("api_key_prefix", sa.String(length=32), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_api_key_hash"), "users", ["api_key_hash"], unique=True)

    # 2. Create matrix_accounts table
    op.create_table(
        "matrix_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("matrix_user_id", sa.String(length=255), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("encrypted_password", sa.Text(), nullable=True),
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
        sa.Column("encryption_nonce", sa.String(length=64), nullable=True),
        sa.Column("crypto_store_blob", sa.LargeBinary(), nullable=True),
        sa.Column("crypto_store_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_matrix_accounts_matrix_user_id"),
        "matrix_accounts",
        ["matrix_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_matrix_accounts_user_id"), "matrix_accounts", ["user_id"], unique=False
    )

    # 3. Create webhooks table
    op.create_table(
        "webhooks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("matrix_room_id", sa.String(length=255), nullable=False),
        sa.Column("matrix_account_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["matrix_account_id"], ["matrix_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_webhooks_matrix_account_id"), "webhooks", ["matrix_account_id"], unique=False
    )
    op.create_index(op.f("ix_webhooks_user_id"), "webhooks", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_webhooks_user_id"), table_name="webhooks")
    op.drop_index(op.f("ix_webhooks_matrix_account_id"), table_name="webhooks")
    op.drop_table("webhooks")
    op.drop_index(op.f("ix_matrix_accounts_user_id"), table_name="matrix_accounts")
    op.drop_index(op.f("ix_matrix_accounts_matrix_user_id"), table_name="matrix_accounts")
    op.drop_table("matrix_accounts")
    op.drop_index(op.f("ix_users_api_key_hash"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
