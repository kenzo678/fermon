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
    Column(
        "quality_profile_id",
        Uuid,
        ForeignKey("quality_profiles.id", name="fk_batches_quality_profile_id"),
        nullable=True,
    ),
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

lab_analyses = Table(
    "lab_analyses",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column(
        "batch_id",
        Uuid,
        ForeignKey("batches.id", name="fk_lab_analyses_batch_id"),
        nullable=False,
    ),
    Column("stage", Text, nullable=False),
    Column("sampled_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("analyst", Text, nullable=True),
    Column("notes", Text, nullable=True),
    # The profile the statuses were judged against when recorded (a snapshot, not a live link).
    Column(
        "quality_profile_id",
        Uuid,
        ForeignKey("quality_profiles.id", name="fk_lab_analyses_quality_profile_id"),
        nullable=True,
    ),
    CheckConstraint(
        "stage IN ('brewhouse', 'maturation', 'bright_beer', 'packaged')",
        name="ck_lab_analyses_stage",
    ),
    Index("ix_lab_analyses_batch_id_sampled_at", "batch_id", "sampled_at"),
)

lab_results = Table(
    "lab_results",
    metadata,
    Column(
        "analysis_id",
        Uuid,
        ForeignKey("lab_analyses.id", name="fk_lab_results_analysis_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("parameter", Text, primary_key=True),
    Column("value", Double, nullable=False),
    Column("status", Text, nullable=False),
    CheckConstraint(
        "status IN ('in_spec', 'warning', 'out_of_spec', 'no_spec')", name="ck_lab_results_status"
    ),
)

quality_profiles = Table(
    "quality_profiles",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    # Names are unique ignoring case, so "Pale lager" and "PALE LAGER" cannot coexist.
    Index("uq_quality_profiles_name", text("lower(name)"), unique=True),
)

quality_specs = Table(
    "quality_specs",
    metadata,
    Column(
        "profile_id",
        Uuid,
        ForeignKey("quality_profiles.id", name="fk_quality_specs_profile_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("stage", Text, primary_key=True),
    # Not constrained in the database: the parameter catalog lives in the domain and may grow.
    Column("parameter", Text, primary_key=True),
    Column("target", Double, nullable=True),
    Column("internal_min", Double, nullable=True),
    Column("internal_max", Double, nullable=True),
    Column("acceptance_min", Double, nullable=True),
    Column("acceptance_max", Double, nullable=True),
    CheckConstraint(
        "stage IN ('brewhouse', 'maturation', 'bright_beer', 'packaged')",
        name="ck_quality_specs_stage",
    ),
    CheckConstraint(
        "acceptance_min IS NOT NULL OR acceptance_max IS NOT NULL",
        name="ck_quality_specs_acceptance",
    ),
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
