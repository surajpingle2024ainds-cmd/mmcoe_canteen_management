# NEW FEATURE: Menu Item Availability Management
# Add to app.py - DO NOT modify existing code

from flask import Blueprint, jsonify, request
from models import db, MenuItem
# DO NOT import get_auth_user at the module level

menu_availability_bp = Blueprint('menu_availability', __name__, url_prefix='/api/kitchen/menu')

@menu_availability_bp.route('/toggle-availability/<int:item_id>', methods=['PUT'])
def toggle_availability(item_id):
    """Toggle menu item availability"""
    from app import get_auth_user
    try:
        user = get_auth_user()
        if not user or user.role not in ['kitchen', 'owner']:
            return jsonify({'error': 'Unauthorized'}), 401
        
        item = MenuItem.query.get(item_id)
        if not item:
            return jsonify({'error': 'Menu item not found'}), 404
        
        item.available = not item.available
        db.session.commit()
        
        return jsonify({
            'success': True,
            'item_id': item_id,
            'available': item.available,
            'message': f'{item.name} is now {"available" if item.available else "unavailable"}'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@menu_availability_bp.route('/set-preparation-time/<int:item_id>', methods=['PUT'])
def set_preparation_time(item_id):
    """Set estimated preparation time for menu item"""
    from app import get_auth_user
    try:
        user = get_auth_user()
        if not user or user.role not in ['kitchen', 'owner']:
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        prep_time = data.get('preparation_time')  # in minutes
        
        item = MenuItem.query.get(item_id)
        if not item:
            return jsonify({'error': 'Menu item not found'}), 404
        
        # Add preparation_time column if doesn't exist
        if not hasattr(MenuItem, 'preparation_time'):
            # Need to run migration: db.Column(db.Integer)
            pass
        
        # For now, store in tags field as "prep:X"
        tags = item.tags or ""
        # Remove old prep time
        tags = ','.join([t for t in tags.split(',') if not t.startswith('prep:')])
        # Add new prep time
        tags += f',prep:{prep_time}'
        item.tags = tags.strip(',')
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Preparation time set to {prep_time} minutes'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@menu_availability_bp.route('/daily-specials', methods=['GET', 'POST'])
def manage_daily_specials():
    """Get or set daily special items"""
    from app import get_auth_user
    try:
        user = get_auth_user()
        if not user or user.role not in ['kitchen', 'owner']:
            return jsonify({'error': 'Unauthorized'}), 401
        
        if request.method == 'GET':
            # Get items tagged as daily special
            specials = MenuItem.query.filter(
                MenuItem.tags.like('%daily-special%')
            ).all()
            
            return jsonify([{
                'id': item.id,
                'name': item.name,
                'icon': item.icon,
                'price': item.price,
                'description': item.description
            } for item in specials]), 200
        
        else:  # POST
            data = request.get_json()
            item_id = data.get('item_id')
            special_price = data.get('special_price')
            
            item = MenuItem.query.get(item_id)
            if not item:
                return jsonify({'error': 'Menu item not found'}), 404
            
            # Add daily-special tag
            tags = item.tags or ""
            if 'daily-special' not in tags:
                item.tags = tags + ',daily-special'
            
            # Update price if provided
            if special_price:
                item.price = special_price
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'{item.name} added to daily specials'
            }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Register blueprint in app.py:
# app.register_blueprint(menu_availability_bp)