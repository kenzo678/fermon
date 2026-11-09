"""create alerts

Revision ID: 0005
Revises: 0004
Create Date: 2026-01-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE alerts (
            id uuid PRIMARY KEY,
            tank_id text NOT NULL,
            batch_id uuid NOT NULL,
            kind text NOT NULL,
            measurement text,
            status text NOT NULL,
            opened_at timestamptz NOT NULL,
            acknowledged_at timestamptz,
            resolved_at timestamptz,
            details jsonb NOT NULL DEFAULT '{}'::jsonb,
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT fk_alerts_tank_id FOREIGN KEY (tank_id) REFERENCES tanks (id),
            CONSTRAINT fk_alerts_batch_id FOREIGN KEY (batch_id) REFERENCES batches (id),
            CONSTRAINT ck_alerts_status CHECK (status IN ('open', 'acknowledged', 'resolved')),
            CONSTRAINT ck_alerts_kind CHECK (kind IN ('out_of_range', 'silent_sensor')),
            CONSTRAINT ck_alerts_measurement_by_kind CHECK (
                (kind = 'out_of_range' AND measurement IS NOT NULL
                    AND measurement IN ('temperature', 'pressure'))
                OR (kind = 'silent_sensor' AND measurement IS NULL)
            )
        )
        """
    )
    # At most one unresolved alert per tank, kind and measurement, whatever the application does.
    # Silent-sensor alerts have a NULL measurement, which a plain unique index treats as distinct,
    # hence the coalesce.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_alerts_one_unresolved
        ON alerts (tank_id, kind, (coalesce(measurement, ''))) WHERE status <> 'resolved'
        """
    )
    op.execute("CREATE INDEX ix_alerts_status_opened_at ON alerts (status, opened_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE alerts")
