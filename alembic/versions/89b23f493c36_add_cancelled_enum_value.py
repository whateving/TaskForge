"""add cancelled enum value

Revision ID: 89b23f493c36
Revises: a3f6407774af
Create Date: 2026-09-13 12:47:24.006264

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '89b23f493c36'
down_revision: Union[str, Sequence[str], None] = 'a3f6407774af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS 'CANCELLED'"
    )

def downgrade() -> None:
    """Downgrade schema."""
    pass
