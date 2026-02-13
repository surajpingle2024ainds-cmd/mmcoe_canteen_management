# NEW FEATURE: Inventory Management for Kitchen
# Add to app.py - DO NOT modify existing code

from flask import Blueprint, jsonify, request
from datetime import datetime
from models import db, InventoryItem, InventoryTransaction
# DO NOT import get_auth_user at module level; instead do:
# def some_route(...):
#     from app import get_auth_user
#     user = get_auth_user()
# ... repeat for every function needing get_auth_user.

inventory_bp = Blueprint('inventory', __name__, url_prefix='/api/kitchen/inventory')

# New Model for Inventory Items
# class InventoryItem(db.Model):
#     __tablename__ = 'inventory_item'
#     id = db.Column(db.Integer, primary_key=True)
#     name = db.Column(db.String(100), nullable=False)
#     category = db.Column(db.String(50))  # vegetables, dairy, spices, etc.
#     quantity = db.Column(db.Float, default=0)
#     unit = db.Column(db.String(20))  # kg, ltr, pcs, etc.
#     low_stock_threshold = db.Column(db.Float, default=10)
#     reorder_quantity = db.Column(db.Float, default=50)
#     cost_per_unit = db.Column(db.Float)
#     last_updated = db.Column(db.DateTime, default=datetime.utcnow)
#     updated_by = db.Column(db.String(100))

# class InventoryTransaction(db.Model):
#     __tablename__ = 'inventory_transaction'
#     id = db.Column(db.Integer, primary_key=True)
#     inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_item.id'), nullable=False)
#     transaction_type = db.Column(db.String(20))  # purchase, usage, wastage, adjustment
#     quantity = db.Column(db.Float)
#     notes = db.Column(db.String(500))
#     created_at = db.Column(db.DateTime, default=datetime.utcnow)
#     created_by = db.Column(db.String(100))
    
#     inventory_item = db.relationship('InventoryItem', backref='transactions')

@inventory_bp.route('/items', methods=['GET'])
def get_inventory_items():
    """Get all inventory items"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role not in ['kitchen', 'owner']:
            return jsonify({'error': 'Unauthorized'}), 401
        
        items = InventoryItem.query.all()
        
        result = [{
            'id': item.id,
            'name': item.name,
            'category': item.category,
            'quantity': item.quantity,
            'unit': item.unit,
            'low_stock_threshold': item.low_stock_threshold,
            'is_low_stock': item.quantity <= item.low_stock_threshold,
            'cost_per_unit': item.cost_per_unit,
            'total_value': (item.quantity * item.cost_per_unit) if item.cost_per_unit else 0,
            'last_updated': item.last_updated.isoformat()
        } for item in items]
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@inventory_bp.route('/items', methods=['POST'])
def add_inventory_item():
    """Add new inventory item"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role not in ['kitchen', 'owner']:
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        
        item = InventoryItem(
            name=data['name'],
            category=data.get('category'),
            quantity=data.get('quantity', 0),
            unit=data.get('unit'),
            low_stock_threshold=data.get('low_stock_threshold', 10),
            reorder_quantity=data.get('reorder_quantity', 50),
            cost_per_unit=data.get('cost_per_unit'),
            updated_by=user.name
        )
        
        db.session.add(item)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Inventory item added',
            'item_id': item.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@inventory_bp.route('/items/<int:item_id>', methods=['PUT'])
def update_inventory_item(item_id):
    """Update inventory quantity"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role not in ['kitchen', 'owner']:
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        item = InventoryItem.query.get(item_id)
        
        if not item:
            return jsonify({'error': 'Item not found'}), 404
        
        old_quantity = item.quantity
        new_quantity = data.get('quantity')
        
        if new_quantity is not None:
            item.quantity = new_quantity
            item.last_updated = datetime.utcnow()
            item.updated_by = user.name
            
            # Record transaction
            transaction = InventoryTransaction(
                inventory_item_id=item_id,
                transaction_type='adjustment',
                quantity=new_quantity - old_quantity,
                notes=data.get('notes', 'Manual adjustment'),
                created_by=user.name
            )
            db.session.add(transaction)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Inventory updated'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@inventory_bp.route('/low-stock', methods=['GET'])
def get_low_stock_items():
    """Get items with low stock"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role not in ['kitchen', 'owner']:
            return jsonify({'error': 'Unauthorized'}), 401
        
        items = InventoryItem.query.filter(
            InventoryItem.quantity <= InventoryItem.low_stock_threshold
        ).all()
        
        result = [{
            'id': item.id,
            'name': item.name,
            'quantity': item.quantity,
            'unit': item.unit,
            'low_stock_threshold': item.low_stock_threshold,
            'reorder_quantity': item.reorder_quantity
        } for item in items]
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@inventory_bp.route('/usage-report', methods=['GET'])
def get_usage_report():
    """Get daily/weekly inventory usage report"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role not in ['kitchen', 'owner']:
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Get usage transactions from last 7 days
        from datetime import timedelta
        week_ago = datetime.utcnow() - timedelta(days=7)
        
        transactions = InventoryTransaction.query.filter(
            InventoryTransaction.transaction_type == 'usage',
            InventoryTransaction.created_at >= week_ago
        ).all()
        
        usage_summary = {}
        for t in transactions:
            item_name = t.inventory_item.name
            if item_name not in usage_summary:
                usage_summary[item_name] = {
                    'name': item_name,
                    'total_used': 0,
                    'unit': t.inventory_item.unit
                }
            usage_summary[item_name]['total_used'] += abs(t.quantity)
        
        return jsonify(list(usage_summary.values())), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Register blueprint in app.py:
# app.register_blueprint(inventory_bp)