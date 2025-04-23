"""add_recipient_id_to_reports

Revision ID: 1c6e1564ddad
Revises: 608c1a56c65b
Create Date: 2025-04-23 13:29:25.343413

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1c6e1564ddad'
down_revision: Union[str, None] = '608c1a56c65b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
