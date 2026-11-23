"""link batches to quality profiles

Revision ID: 0007
Revises: 0006
Create Date: 2026-01-07
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable: existing batches keep working without a profile.
    op.execute(
        """
        ALTER TABLE batches
        ADD COLUMN quality_profile_id uuid,
        ADD CONSTRAINT fk_batches_quality_profile_id FOREIGN KEY (quality_profile_id)
            REFERENCES quality_profiles (id)
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE batches DROP COLUMN quality_profile_id")
