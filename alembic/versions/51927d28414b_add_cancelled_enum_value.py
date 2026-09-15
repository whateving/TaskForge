"""add cancelled enum value

Revision ID: 51927d28414b
Revises: 89b23f493c36
Create Date: 2026-09-13 12:49:46.915095

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '51927d28414b'
down_revision: Union[str, Sequence[str], None] = '89b23f493c36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
