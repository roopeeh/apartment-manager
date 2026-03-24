"""add is_rental to flats

Revision ID: 002
Revises: 001
Create Date: 2026-03-23

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    # Add is_rental column to flats table
    op.add_column('flats', sa.Column('is_rental', sa.Boolean(), nullable=True))
    
    # Set default value for existing rows
    op.execute('UPDATE flats SET is_rental = false WHERE is_rental IS NULL')
    
    # Make the column non-nullable after setting defaults
    op.alter_column('flats', 'is_rental', nullable=False, server_default=sa.false())


def downgrade():
    # Remove is_rental column from flats table
    op.drop_column('flats', 'is_rental')
