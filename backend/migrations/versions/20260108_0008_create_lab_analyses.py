"""create lab analyses and their results

Revision ID: 0008
Revises: 0007
Create Date: 2026-01-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE lab_analyses (
            id uuid PRIMARY KEY,
            batch_id uuid NOT NULL,
            stage text NOT NULL,
            sampled_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL,
            analyst text,
            notes text,
            quality_profile_id uuid,
            CONSTRAINT fk_lab_analyses_batch_id FOREIGN KEY (batch_id) REFERENCES batches (id),
            CONSTRAINT fk_lab_analyses_quality_profile_id FOREIGN KEY (quality_profile_id)
                REFERENCES quality_profiles (id),
            CONSTRAINT ck_lab_analyses_stage
                CHECK (stage IN ('brewhouse', 'maturation', 'bright_beer', 'packaged'))
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_lab_analyses_batch_id_sampled_at ON lab_analyses (batch_id, sampled_at)"
    )
    op.execute(
        """
        CREATE TABLE lab_results (
            analysis_id uuid NOT NULL,
            parameter text NOT NULL,
            value double precision NOT NULL,
            status text NOT NULL,
            PRIMARY KEY (analysis_id, parameter),
            CONSTRAINT fk_lab_results_analysis_id FOREIGN KEY (analysis_id)
                REFERENCES lab_analyses (id) ON DELETE CASCADE,
            CONSTRAINT ck_lab_results_status
                CHECK (status IN ('in_spec', 'warning', 'out_of_spec', 'no_spec'))
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE lab_results")
    op.execute("DROP TABLE lab_analyses")
