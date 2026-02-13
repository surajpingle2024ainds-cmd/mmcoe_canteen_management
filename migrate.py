import sqlite3

# Connect to database
conn = sqlite3.connect('canteen.db')
cursor = conn.cursor()

try:
    # Add missing tags column
    cursor.execute('ALTER TABLE menu_item ADD COLUMN tags VARCHAR(100)')
    conn.commit()
    print("✅ Successfully added 'tags' column to menu_item table")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e):
        print("✅ Column 'tags' already exists")
    else:
        print(f"❌ Error: {e}")
finally:
    conn.close()