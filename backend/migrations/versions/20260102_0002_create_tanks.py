"""create tanks

Revision ID: 0002
Revises: 0001
Create Date: 2026-01-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Deliberately no foreign key from readings.tank_id to tanks.id: readings is a hypertable
    # (FKs from it cost a lookup per inserted row and complicate chunk management), and ingestion
    # registers the tank before storing its reading, so the application keeps them consistent.
    op.execute(
        """
        CREATE TABLE tanks (
            id text PRIMARY KEY,
            display_name text,
            first_seen_at timestamptz NOT NULL
        )
        """
    )
    # Tanks that already reported readings before this table existed.
    op.execute(
        """
        INSERT INTO tanks (id, first_seen_at)
        SELECT tank_id, min(recorded_at) FROM readings GROUP BY tank_id
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE tanks")
