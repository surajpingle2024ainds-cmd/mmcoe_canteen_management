import sqlite3
try:
    conn = sqlite3.connect('canteen.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print("Tables found:", tables)
    conn.close()
except Exception as e:
    print(f"Error: {e}")
