"""create attendance table

Revision ID: 1f90364d8767
Revises: 542bf2f2d480
Create Date: 2026-03-19 14:19:25.857039

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1f90364d8767'
down_revision = '542bf2f2d480'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
	'attendance',
	sa.Column('id', sa.Integer, primary_key=True),
	sa.Column('user_id', sa.Integer, sa.ForeignKey('user.id')),
	sa.Column('date', sa.Date, nullable=False),
	sa.Column('type', sa.String(50), nullable=False),
	sa.Column('start_time', sa.Time),
	sa.Column('end_time', sa.Time),
	sa.Column('duration_minutes', sa.Integer),
	sa.Column('reason', sa.String(200)),
	sa.Column('status', sa.String(50)),
)


def downgrade():
    op.drop_table('attendance')
