"""Dump all table names from the database using SQLAlchemy."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import app
from sqlalchemy import inspect

try:
    with app.app_context():
        inspector = inspect(app.extensions['sqlalchemy'].engine)
        tables = inspector.get_table_names()
        print(f"Tables found ({len(tables)}):")
        for t in tables:
            print(f"  - {t}")
except Exception as e:
    print(f"Error: {e}")
