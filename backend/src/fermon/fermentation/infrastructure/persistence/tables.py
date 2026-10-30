from sqlalchemy import (
    Column,
    DateTime,
    Double,
    Index,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    desc,
)

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
