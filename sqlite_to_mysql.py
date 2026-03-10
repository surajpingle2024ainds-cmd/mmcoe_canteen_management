"""
One-time migration script: SQLite → MySQL

Reads all data from the old SQLite database and inserts it into the
MySQL database configured in app.py.

Usage:
  1. Make sure MySQL is running and the database exists.
  2. Run:  python sqlite_to_mysql.py [path_to_sqlite_db]
     Default SQLite path: instance/canteen_v3.db
"""
import sys
import os
import sqlite3

sys.path.insert(0, os.path.dirname(__file__))

from app import app
from models import db
from sqlalchemy import inspect, text


def migrate_data(sqlite_path: str):
    """Transfer all table data from SQLite to MySQL."""
    # --- Connect to SQLite source ---
    if not os.path.exists(sqlite_path):
        print(f"❌ SQLite database not found at: {sqlite_path}")
        print("   Please provide the correct path as an argument.")
        sys.exit(1)

    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row
    src_cursor = src.cursor()

    # Get list of tables in SQLite
    src_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [row[0] for row in src_cursor.fetchall()]
    print(f"📋 Found {len(tables)} tables in SQLite: {', '.join(tables)}")

    with app.app_context():
        # Ensure MySQL tables exist
        db.create_all()

        # Get list of MySQL tables for validation
        inspector = inspect(db.engine)
        mysql_tables = set(inspector.get_table_names())

        for table_name in tables:
            if table_name not in mysql_tables:
                print(f"⚠️  Skipping '{table_name}' — not found in MySQL schema")
                continue

            # Read all rows from SQLite
            src_cursor.execute(f'SELECT * FROM "{table_name}"')
            columns = [desc[0] for desc in src_cursor.description]
            rows = src_cursor.fetchall()

            if not rows:
                print(f"⏭️  '{table_name}' — empty, skipping")
                continue

            # Build INSERT statement
            col_list = ', '.join(f'`{c}`' for c in columns)
            placeholders = ', '.join(f':{c}' for c in columns)
            insert_sql = text(f"INSERT INTO `{table_name}` ({col_list}) VALUES ({placeholders})")

            # Insert rows in batches
            batch_size = 500
            inserted = 0
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]
                row_dicts = [dict(zip(columns, row)) for row in batch]
                try:
                    db.session.execute(insert_sql, row_dicts)
                    db.session.commit()
                    inserted += len(batch)
                except Exception as e:
                    db.session.rollback()
                    print(f"❌ Error inserting into '{table_name}': {e}")
                    break

            print(f"✅ '{table_name}' — migrated {inserted}/{len(rows)} rows")

    src.close()
    print("\n🎉 Migration complete!")


if __name__ == '__main__':
    # Default SQLite path — adjust if your DB is elsewhere
    default_path = os.path.join(os.path.dirname(__file__), 'instance', 'canteen_v3.db')
    sqlite_db = sys.argv[1] if len(sys.argv) > 1 else default_path
    print(f"🔄 Migrating data from: {sqlite_db}")
    migrate_data(sqlite_db)
