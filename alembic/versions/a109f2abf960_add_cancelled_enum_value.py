"""add cancelled enum value

Revision ID: a109f2abf960
Revises: 51927d28414b
Create Date: 2026-09-13 12:50:38.083428

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a109f2abf960'
down_revision: Union[str, Sequence[str], None] = '51927d28414b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS 'CANCELLED'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    pass
