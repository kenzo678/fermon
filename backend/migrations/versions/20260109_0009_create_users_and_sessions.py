"""create users and sessions

Revision ID: 0009
Revises: 0008
Create Date: 2026-01-09
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE users (
            id uuid PRIMARY KEY,
            email text NOT NULL,
            display_name text NOT NULL,
            role text NOT NULL,
            password_hash text NOT NULL,
            must_change_password boolean NOT NULL DEFAULT false,
            active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL,
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT ck_users_role CHECK (role IN ('admin', 'brewer', 'viewer'))
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX uq_users_email_lower ON users (lower(email))")
    # Only the SHA-256 of the token is stored; the primary key is the lookup index.
    op.execute(
        """
        CREATE TABLE sessions (
            token_hash text PRIMARY KEY,
            user_id uuid NOT NULL,
            created_at timestamptz NOT NULL,
            expires_at timestamptz NOT NULL,
            revoked_at timestamptz,
            CONSTRAINT fk_sessions_user_id FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    op.execute("CREATE INDEX ix_sessions_user_id ON sessions (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE sessions")
    op.execute("DROP TABLE users")
