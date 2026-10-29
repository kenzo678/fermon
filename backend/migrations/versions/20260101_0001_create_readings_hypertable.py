"""create readings hypertable

Revision ID: 0001
Revises:
Create Date: 2026-01-01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    op.execute(
        """
        CREATE TABLE readings (
            tank_id text NOT NULL,
            sensor_id text NOT NULL,
            measurement text NOT NULL,
            value double precision NOT NULL,
            unit text NOT NULL,
            recorded_at timestamptz NOT NULL,
            CONSTRAINT uq_readings_identity
                UNIQUE (tank_id, sensor_id, measurement, recorded_at)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_readings_tank_id_recorded_at ON readings (tank_id, recorded_at DESC)"
    )
    op.execute("SELECT create_hypertable('readings', by_range('recorded_at'))")


def downgrade() -> None:
    op.execute("DROP TABLE readings")
