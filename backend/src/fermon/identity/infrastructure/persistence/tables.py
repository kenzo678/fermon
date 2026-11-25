from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    Uuid,
    text,
)

# Own MetaData: this bounded context owns its tables; Alembic compares both metadata objects.
identity_metadata = MetaData()

users = Table(
    "users",
    identity_metadata,
    Column("id", Uuid, primary_key=True),
    Column("email", Text, nullable=False),
    Column("display_name", Text, nullable=False),
    Column("role", Text, nullable=False),
    Column("password_hash", Text, nullable=False),
    Column("must_change_password", Boolean, nullable=False, server_default=text("false")),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False, server_default=text("1")),
    CheckConstraint("role IN ('admin', 'brewer', 'viewer')", name="ck_users_role"),
    Index("uq_users_email_lower", text("lower(email)"), unique=True),
)

# Only the SHA-256 of the session token is stored (the primary key doubles as the lookup index).
sessions = Table(
    "sessions",
    identity_metadata,
    Column("token_hash", Text, primary_key=True),
    Column("user_id", Uuid, ForeignKey("users.id", name="fk_sessions_user_id"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    Index("ix_sessions_user_id", "user_id"),
)
