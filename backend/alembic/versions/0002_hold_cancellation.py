"""Persist cancellation distinctly from hold expiry."""
from alembic import op
import sqlalchemy as sa
revision='0002_hold_cancellation'
down_revision='0001'
branch_labels=None
depends_on=None

def upgrade():
    # Initial revision creates metadata on new installs; allow either upgrade path.
    columns={c['name'] for c in sa.inspect(op.get_bind()).get_columns('booking_holds')}
    if 'cancelled_at' not in columns:
        op.add_column('booking_holds',sa.Column('cancelled_at',sa.DateTime(),nullable=True))

def downgrade():
    op.drop_column('booking_holds','cancelled_at')
