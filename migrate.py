"""
Database migration helper using Flask-Migrate (Alembic).
Run schema migrations via SQLAlchemy instead of raw SQL.

Usage:
  python migrate.py          # Apply any pending schema changes
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import app
from models import db

def migrate():
    """Create all tables and apply schema from models.py."""
    with app.app_context():
        db.create_all()
        print("✅ All database tables created/updated successfully.")

if __name__ == '__main__':
    migrate()