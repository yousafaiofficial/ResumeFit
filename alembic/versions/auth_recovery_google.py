"""Add Google identities and expiring authentication challenges."""

import alembic.op as op
import sqlalchemy as sa

revision = "auth_recovery_google"
down_revision = "phase12_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_identities",
        sa.Column("subject", sa.String(255), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
    )
    op.create_table(
        "auth_challenges",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("verifier", sa.String(128)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_challenges_user_id", "auth_challenges", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_auth_challenges_user_id", table_name="auth_challenges")
    op.drop_table("auth_challenges")
    op.drop_table("google_identities")
