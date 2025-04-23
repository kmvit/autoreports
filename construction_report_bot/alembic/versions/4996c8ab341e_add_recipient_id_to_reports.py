"""add_recipient_id_to_reports

Revision ID: 4996c8ab341e
Revises: 1c6e1564ddad
Create Date: 2025-04-23 13:30:01.627457

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4996c8ab341e'
down_revision: Union[str, None] = '1c6e1564ddad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Добавляем поле recipient_id в таблицу reports
    op.add_column('reports', sa.Column('recipient_id', sa.Integer(), nullable=True))
    # Добавляем внешний ключ
    op.create_foreign_key(
        'fk_reports_recipient_id_users',
        'reports', 'users',
        ['recipient_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Удаляем внешний ключ
    op.drop_constraint('fk_reports_recipient_id_users', 'reports', type_='foreignkey')
    # Удаляем поле recipient_id
    op.drop_column('reports', 'recipient_id')
