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
