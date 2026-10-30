"""create reading continuous aggregates

Revision ID: 0003
Revises: 0002
Create Date: 2026-01-03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous) cannot run inside a transaction
    # block, so this runs in Alembic's autocommit block. Not atomic: a failure midway can leave
    # readings_1m behind; downgrade drops with IF EXISTS so it can be re-run.
    with op.get_context().autocommit_block():
        # Statistics of one measurement per minute, ALL sensors of that measurement together
        # (a tank may have several probes; the dashboard charts the tank, not each probe).
        # Stores sum (not avg) so the hourly level can compute an exact weighted average:
        # avg = sum / count. Averaging minute averages would be wrong when minutes hold
        # different numbers of readings.
        # materialized_only = false: queries also aggregate the not-yet-materialized newest
        # data on the fly, so charts include readings newer than the last refresh.
        # WITH DATA materializes the history that exists when the migration runs.
        op.execute(
            """
            CREATE MATERIALIZED VIEW readings_1m
            WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
            SELECT
                time_bucket('1 minute', recorded_at) AS bucket,
                tank_id,
                measurement,
                sum(value) AS sum_value,
                min(value) AS min_value,
                max(value) AS max_value,
                count(*) AS sample_count
            FROM readings
            GROUP BY 1, 2, 3
            """
        )
        # Hierarchical: built on readings_1m, so refreshing it never rescans raw readings.
        op.execute(
            """
            CREATE MATERIALIZED VIEW readings_1h
            WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
            SELECT
                time_bucket('1 hour', bucket) AS bucket,
                tank_id,
                measurement,
                sum(sum_value) AS sum_value,
                min(min_value) AS min_value,
                max(max_value) AS max_value,
                sum(sample_count)::bigint AS sample_count
            FROM readings_1m
            GROUP BY 1, 2, 3
            """
        )
        # Refresh policies. end_offset leaves the newest, still-filling bucket(s) to real-time
        # aggregation instead of materializing them repeatedly. start_offset bounds the work per
        # run to recent data: readings older than the window (late backfills) are not picked up
        # automatically; run refresh_continuous_aggregate() by hand for those.
        op.execute(
            """
            SELECT add_continuous_aggregate_policy(
                'readings_1m',
                start_offset => INTERVAL '2 hours',
                end_offset => INTERVAL '1 minute',
                schedule_interval => INTERVAL '1 minute'
            )
            """
        )
        op.execute(
            """
            SELECT add_continuous_aggregate_policy(
                'readings_1h',
                start_offset => INTERVAL '3 days',
                end_offset => INTERVAL '1 hour',
                schedule_interval => INTERVAL '30 minutes'
            )
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        # Remove the refresh jobs first so a scheduled run does not race the DROP (it can fail
        # with "tuple concurrently deleted"). Then the child before its parent: readings_1h is
        # built on readings_1m.
        op.execute("SELECT remove_continuous_aggregate_policy('readings_1h', if_exists => true)")
        op.execute("SELECT remove_continuous_aggregate_policy('readings_1m', if_exists => true)")
        op.execute("DROP MATERIALIZED VIEW IF EXISTS readings_1h")
        op.execute("DROP MATERIALIZED VIEW IF EXISTS readings_1m")
