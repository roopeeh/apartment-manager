"""Run database migrations directly"""
import os
import sys
import asyncio
from alembic.config import Config
from alembic import command

# Set DATABASE_URL
os.environ['DATABASE_URL'] = "postgresql+asyncpg://appadmin:ApartmentManager@2024!@apartment-manager-public-dev.c8jm4a2as20x.us-east-1.rds.amazonaws.com:5432/apartment_manager"

# Run migrations
alembic_cfg = Config("alembic.ini")
command.upgrade(alembic_cfg, "head")
print("✅ Migrations completed successfully!")
