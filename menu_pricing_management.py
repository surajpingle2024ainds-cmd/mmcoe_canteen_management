# NEW FEATURE: Menu & Pricing Management for Owner
# Add to app.py - DO NOT modify existing code

from flask import Blueprint, jsonify, request
from datetime import datetime

from sqlalchemy import func
from models import db, MenuItem
# DO NOT import get_auth_user at module level

menu_management_bp = Blueprint('menu_management', __name__, url_prefix='/api/owner/menu')

@menu_management_bp.route('/items', methods=['GET'])
def get_all_menu_items():
    """Get all menu items for management"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        items = MenuItem.query.all()
        
        return jsonify([{
            'id': item.id,
            'name': item.name,
            'icon': item.icon,
            'price': item.price,
            'description': item.description,
            'category': item.category,
            'available': item.available,
            'tags': item.tags
        } for item in items]), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@menu_management_bp.route('/items', methods=['POST'])
def add_menu_item():
    """Add new menu item"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        
        item = MenuItem(
            name=data['name'],
            icon=data.get('icon', '🍽️'),
            price=float(data['price']),
            description=data.get('description', ''),
            category=data.get('category', 'General'),
            available=data.get('available', True),
            tags=data.get('tags', '')
        )
        
        db.session.add(item)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Menu item added successfully',
            'item_id': item.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@menu_management_bp.route('/items/<int:item_id>', methods=['PUT'])
def update_menu_item(item_id):
    """Update existing menu item"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        item = MenuItem.query.get(item_id)
        
        if not item:
            return jsonify({'error': 'Menu item not found'}), 404
        
        # Update fields
        if 'name' in data:
            item.name = data['name']
        if 'icon' in data:
            item.icon = data['icon']
        if 'price' in data:
            item.price = float(data['price'])
        if 'description' in data:
            item.description = data['description']
        if 'category' in data:
            item.category = data['category']
        if 'available' in data:
            item.available = data['available']
        if 'tags' in data:
            item.tags = data['tags']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Menu item updated successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@menu_management_bp.route('/items/<int:item_id>', methods=['DELETE'])
def delete_menu_item(item_id):
    """Archive/delete menu item"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        item = MenuItem.query.get(item_id)
        
        if not item:
            return jsonify({'error': 'Menu item not found'}), 404
        
        # Instead of deleting, mark as unavailable
        item.available = False
        item.tags = (item.tags or '') + ',archived'
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Menu item archived successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@menu_management_bp.route('/bulk-price-update', methods=['POST'])
def bulk_price_update():
    """Update prices for multiple items"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        update_type = data.get('type')  # percentage or fixed
        value = float(data.get('value', 0))
        category = data.get('category')  # optional
        
        query = MenuItem.query
        if category:
            query = query.filter_by(category=category)
        
        items = query.all()
        
        for item in items:
            if update_type == 'percentage':
                item.price = round(item.price * (1 + value / 100), 2)
            elif update_type == 'fixed':
                item.price = round(item.price + value, 2)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'{len(items)} items updated',
            'items_updated': len(items)
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@menu_management_bp.route('/categories', methods=['GET'])
def get_categories():
    """Get all menu categories"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        categories = db.session.query(
            MenuItem.category,
            func.count(MenuItem.id).label('item_count')
        ).group_by(MenuItem.category).all()
        
        return jsonify([{
            'name': c.category,
            'item_count': int(c.item_count)
        } for c in categories]), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Register blueprint in app.py:
# app.register_blueprint(menu_management_bp)