"""create quality profiles and specs

Revision ID: 0006
Revises: 0005
Create Date: 2026-01-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE quality_profiles (
            id uuid PRIMARY KEY,
            name text NOT NULL,
            description text,
            created_at timestamptz NOT NULL
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX uq_quality_profiles_name ON quality_profiles (lower(name))")
    op.execute(
        """
        CREATE TABLE quality_specs (
            profile_id uuid NOT NULL,
            stage text NOT NULL,
            parameter text NOT NULL,
            target double precision,
            internal_min double precision,
            internal_max double precision,
            acceptance_min double precision,
            acceptance_max double precision,
            PRIMARY KEY (profile_id, stage, parameter),
            CONSTRAINT fk_quality_specs_profile_id FOREIGN KEY (profile_id)
                REFERENCES quality_profiles (id) ON DELETE CASCADE,
            CONSTRAINT ck_quality_specs_stage
                CHECK (stage IN ('brewhouse', 'maturation', 'bright_beer', 'packaged')),
            CONSTRAINT ck_quality_specs_acceptance
                CHECK (acceptance_min IS NOT NULL OR acceptance_max IS NOT NULL)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE quality_specs")
    op.execute("DROP TABLE quality_profiles")
