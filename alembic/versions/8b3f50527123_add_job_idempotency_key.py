"""add job idempotency key

Revision ID: 8b3f50527123
Revises: 2bc955db811c
Create Date: 2026-09-11 20:06:34.472491

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from uuid import uuid4



# revision identifiers, used by Alembic.
revision: str = '8b3f50527123'
down_revision: Union[str, Sequence[str], None] = '2bc955db811c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


from uuid import uuid4

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "idempotency_key",
            sa.String(length=255),
            nullable=True,
        ),
    )

    connection = op.get_bind()

    jobs = connection.execute(
        sa.text("SELECT id FROM jobs WHERE idempotency_key IS NULL")
    ).fetchall()

    for job in jobs:
        connection.execute(
            sa.text(
                """
                UPDATE jobs
                SET idempotency_key = :key
                WHERE id = :id
                """
            ),
            {
                "id": job.id,
                "key": str(uuid4()),
            },
        )

    op.alter_column(
        "jobs",
        "idempotency_key",
        existing_type=sa.String(length=255),
        nullable=False,
    )

    # Ensures two jobs can never share the same idempotency key in the database going forward.
    op.create_unique_constraint(
        "uq_jobs_idempotency_key",
        "jobs",
        ["idempotency_key"],
    )

"""
1. Add the column temporarily as nullable
2. Give existing jobs unique UUID values
3. Make the column NOT NULL
4. Add a UNIQUE constraint
"""

def downgrade() -> None:
    op.drop_constraint(
        "uq_jobs_idempotency_key",
        "jobs",
        type_="unique",
    )

    op.drop_column(
        "jobs",
        "idempotency_key",
    )