"""change_report_equipment_to_many_to_many

Revision ID: 608c1a56c65b
Revises: a517804269e9
Create Date: 2025-04-22 17:00:41.452746

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '608c1a56c65b'
down_revision: Union[str, None] = 'a517804269e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('report_equipment', 'report_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.alter_column('report_equipment', 'equipment_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.drop_column('report_equipment', 'id')
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('report_equipment', sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False))
    op.alter_column('report_equipment', 'equipment_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('report_equipment', 'report_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    # ### end Alembic commands ###
