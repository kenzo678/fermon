"""create batches

Revision ID: 0004
Revises: 0003
Create Date: 2026-01-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE batches (
            id uuid PRIMARY KEY,
            tank_id text NOT NULL,
            beer_name text NOT NULL,
            style text NOT NULL,
            template text NOT NULL,
            status text NOT NULL,
            temperature_min double precision NOT NULL,
            temperature_max double precision NOT NULL,
            pressure_max double precision NOT NULL,
            pressure_min double precision,
            expected_final_abv double precision,
            planned_start timestamptz NOT NULL,
            expected_end timestamptz,
            started_at timestamptz,
            finished_at timestamptz,
            notes text,
            created_at timestamptz NOT NULL,
            version integer NOT NULL DEFAULT 1,
            CONSTRAINT fk_batches_tank_id FOREIGN KEY (tank_id) REFERENCES tanks (id),
            CONSTRAINT ck_batches_status CHECK (status IN ('planned', 'active', 'finished')),
            CONSTRAINT ck_batches_template CHECK (template IN ('ale', 'lager', 'custom'))
        )
        """
    )
    # The invariant "one active batch per tank" lives in the database too, so concurrent starts
    # cannot both succeed whatever the application does.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_batches_one_active_per_tank
        ON batches (tank_id) WHERE status = 'active'
        """
    )
    op.execute("CREATE INDEX ix_batches_tank_id_created_at ON batches (tank_id, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE batches")
