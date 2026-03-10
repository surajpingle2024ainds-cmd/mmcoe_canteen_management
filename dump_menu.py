"""Dump all menu items from the database to JSON using SQLAlchemy."""
import sys
import os
import json
sys.path.insert(0, os.path.dirname(__file__))

from app import app
from models import MenuItem

try:
    with app.app_context():
        items = MenuItem.query.all()
        data = []
        for item in items:
            data.append({
                'id': item.id,
                'name': item.name,
                'icon': item.icon,
                'price': item.price,
                'description': item.description,
                'category': item.category,
                'available': item.available,
                'tags': item.tags,
                'image_url': item.image_url
            })

        with open('menu_dump.json', 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Dumped {len(data)} items to menu_dump.json")
except Exception as e:
    print(f"Error: {e}")
