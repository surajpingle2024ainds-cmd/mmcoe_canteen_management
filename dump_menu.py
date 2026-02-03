import sqlite3
import json

try:
    conn = sqlite3.connect('instance/canteen.db')
    cursor = conn.cursor()
    # Get all columns for menu_item
    cursor.execute("SELECT * FROM menu_item")
    columns = [description[0] for description in cursor.description]
    rows = cursor.fetchall()
    
    items = []
    for row in rows:
        item = dict(zip(columns, row))
        items.append(item)
        
    with open('menu_dump.json', 'w') as f:
        json.dump(items, f, indent=2)
    print("Dumped to menu_dump.json")
    conn.close()
except Exception as e:
    print(f"Error: {e}")
