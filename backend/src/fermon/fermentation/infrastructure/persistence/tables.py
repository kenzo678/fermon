from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    desc,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

# Timescale requires the partitioning column (recorded_at) in every unique index.
readings = Table(
    "readings",
    metadata,
    Column("tank_id", Text, nullable=False),
    Column("sensor_id", Text, nullable=False),
    Column("measurement", Text, nullable=False),
    Column("value", Double, nullable=False),
    Column("unit", Text, nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "tank_id",
        "sensor_id",
        "measurement",
        "recorded_at",
        name="uq_readings_identity",
    ),
    Index("ix_readings_tank_id_recorded_at", "tank_id", desc("recorded_at")),
)

# No foreign key from readings.tank_id: readings is a hypertable (an FK to a plain table slows
# every chunk insert and complicates chunk management), and the ingest flow already registers the
# tank before storing its reading, so the application keeps the two consistent.
tanks = Table(
    "tanks",
    metadata,
    Column("id", Text, primary_key=True),
    Column("display_name", Text, nullable=True),
    Column("first_seen_at", DateTime(timezone=True), nullable=False),
)

batches = Table(
    "batches",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tank_id", Text, ForeignKey("tanks.id", name="fk_batches_tank_id"), nullable=False),
    Column("beer_name", Text, nullable=False),
    Column("style", Text, nullable=False),
    Column("template", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("temperature_min", Double, nullable=False),
    Column("temperature_max", Double, nullable=False),
    Column("pressure_max", Double, nullable=False),
    Column("pressure_min", Double, nullable=True),
    Column("expected_final_abv", Double, nullable=True),
    Column("planned_start", DateTime(timezone=True), nullable=False),
    Column("expected_end", DateTime(timezone=True), nullable=True),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("notes", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False, server_default=text("1")),
    CheckConstraint("status IN ('planned', 'active', 'finished')", name="ck_batches_status"),
    CheckConstraint("template IN ('ale', 'lager', 'custom')", name="ck_batches_template"),
    Index(
        "uq_batches_one_active_per_tank",
        "tank_id",
        unique=True,
        postgresql_where=text("status = 'active'"),
    ),
    Index("ix_batches_tank_id_created_at", "tank_id", desc("created_at")),
)

alerts = Table(
    "alerts",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tank_id", Text, ForeignKey("tanks.id", name="fk_alerts_tank_id"), nullable=False),
    Column("batch_id", Uuid, ForeignKey("batches.id", name="fk_alerts_batch_id"), nullable=False),
    Column("kind", Text, nullable=False),
    Column("measurement", Text, nullable=True),
    Column("status", Text, nullable=False),
    Column("opened_at", DateTime(timezone=True), nullable=False),
    Column("acknowledged_at", DateTime(timezone=True), nullable=True),
    Column("resolved_at", DateTime(timezone=True), nullable=True),
    Column("details", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("version", Integer, nullable=False, server_default=text("1")),
    CheckConstraint("status IN ('open', 'acknowledged', 'resolved')", name="ck_alerts_status"),
    CheckConstraint("kind IN ('out_of_range', 'silent_sensor')", name="ck_alerts_kind"),
    CheckConstraint(
        "(kind = 'out_of_range' AND measurement IS NOT NULL "
        "AND measurement IN ('temperature', 'pressure')) "
        "OR (kind = 'silent_sensor' AND measurement IS NULL)",
        name="ck_alerts_measurement_by_kind",
    ),
    # One unresolved alert per (tank, kind, measurement); silent alerts have a NULL measurement,
    # which a plain unique index would treat as distinct, hence the coalesce.
    Index(
        "uq_alerts_one_unresolved",
        "tank_id",
        "kind",
        text("(coalesce(measurement, ''))"),
        unique=True,
        postgresql_where=text("status <> 'resolved'"),
    ),
    Index("ix_alerts_status_opened_at", "status", desc("opened_at")),
)


# Continuous aggregates created by migration 0003 (see it for the semantics). They are views, not
# tables to migrate, so they live in their own MetaData: Alembic autogenerate must not manage them.
aggregates_metadata = MetaData()


def _aggregate_view(name: str) -> Table:
    return Table(
        name,
        aggregates_metadata,
        Column("bucket", DateTime(timezone=True)),
        Column("tank_id", Text),
        Column("measurement", Text),
        Column("sum_value", Double),
        Column("min_value", Double),
        Column("max_value", Double),
        Column("sample_count", BigInteger),
    )


readings_1m = _aggregate_view("readings_1m")
readings_1h = _aggregate_view("readings_1h")
