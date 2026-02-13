# NEW FEATURE: Real-Time Order Display for Kitchen
# Add to app.py - DO NOT modify existing code

from flask import Blueprint, jsonify, request
from datetime import datetime
from models import db, Order, OrderItem, MenuItem, KitchenOrderStatus
# DO NOT import get_auth_user at module level

kitchen_orders_bp = Blueprint('kitchen_orders', __name__, url_prefix='/api/kitchen')

# Remove KitchenOrderStatus model (now in models.py)
# New Model for Kitchen Order Status
# class KitchenOrderStatus(db.Model):
#     __tablename__ = 'kitchen_order_status'
#     id = db.Column(db.Integer, primary_key=True)
#     order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False, unique=True)
#     status = db.Column(db.String(20), default='pending')  # pending, in_progress, ready, completed
#     priority = db.Column(db.String(10), default='regular')  # regular, urgent
#     assigned_staff = db.Column(db.String(100))
#     preparation_started_at = db.Column(db.DateTime)
#     preparation_completed_at = db.Column(db.DateTime)
#     estimated_time = db.Column(db.Integer)  # in minutes
#     notes = db.Column(db.String(500))
#     created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
#     order = db.relationship('Order', backref='kitchen_status')

@kitchen_orders_bp.route('/orders/live', methods=['GET'])
def get_live_orders():
    """Get all orders for kitchen with real-time status"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role not in ['kitchen', 'owner']:
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Get orders that are not delivered or rejected
        orders = Order.query.filter(
            Order.status.in_(['pending', 'accepted', 'preparing', 'ready'])
        ).order_by(Order.created_at.desc()).all()
        
        result = []
        for order in orders:
            kitchen_status = KitchenOrderStatus.query.filter_by(order_id=order.id).first()
            
            result.append({
                'order_id': order.order_id,
                'id': order.id,
                'customer_name': order.customer_name,
                'customer_phone': order.customer_phone,
                'items': [{
                    'name': item.menu_item.name,
                    'icon': item.menu_item.icon,
                    'quantity': item.quantity,
                    'price': item.price
                } for item in order.items],
                'total': order.total_amount,
                'status': kitchen_status.status if kitchen_status else 'pending',
                'priority': kitchen_status.priority if kitchen_status else 'regular',
                'assigned_staff': kitchen_status.assigned_staff if kitchen_status else None,
                'estimated_time': kitchen_status.estimated_time if kitchen_status else None,
                'created_at': order.created_at.isoformat(),
                'preparation_started_at': kitchen_status.preparation_started_at.isoformat() if kitchen_status and kitchen_status.preparation_started_at else None
            })
        
        return jsonify(result), 200
        
    except Exception as e:
        print(f"Kitchen Orders Error: {e}")
        return jsonify({'error': str(e)}), 500

@kitchen_orders_bp.route('/orders/<int:order_id>/status', methods=['PUT'])
def update_order_status(order_id):
    """Update kitchen order status"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role not in ['kitchen', 'owner']:
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        new_status = data.get('status')
        
        if new_status not in ['pending', 'in_progress', 'ready', 'completed']:
            return jsonify({'error': 'Invalid status'}), 400
        
        order = Order.query.get(order_id)
        if not order:
            return jsonify({'error': 'Order not found'}), 404
        
        kitchen_status = KitchenOrderStatus.query.filter_by(order_id=order_id).first()
        
        if not kitchen_status:
            kitchen_status = KitchenOrderStatus(
                order_id=order_id,
                status=new_status
            )
            db.session.add(kitchen_status)
        else:
            kitchen_status.status = new_status
        
        # Update timestamps
        if new_status == 'in_progress' and not kitchen_status.preparation_started_at:
            kitchen_status.preparation_started_at = datetime.utcnow()
        elif new_status == 'ready':
            kitchen_status.preparation_completed_at = datetime.utcnow()
            order.status = 'ready'
        elif new_status == 'completed':
            order.status = 'delivered'
        
        # Update assigned staff
        if data.get('assigned_staff'):
            kitchen_status.assigned_staff = data.get('assigned_staff')
        
        # Update notes
        if data.get('notes'):
            kitchen_status.notes = data.get('notes')
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Order status updated to {new_status}'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Status Update Error: {e}")
        return jsonify({'error': str(e)}), 500

@kitchen_orders_bp.route('/orders/<int:order_id>/priority', methods=['PUT'])
def update_order_priority(order_id):
    """Mark order as urgent or regular"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role not in ['kitchen', 'owner']:
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        priority = data.get('priority', 'regular')
        
        if priority not in ['regular', 'urgent']:
            return jsonify({'error': 'Invalid priority'}), 400
        
        kitchen_status = KitchenOrderStatus.query.filter_by(order_id=order_id).first()
        
        if not kitchen_status:
            kitchen_status = KitchenOrderStatus(
                order_id=order_id,
                priority=priority
            )
            db.session.add(kitchen_status)
        else:
            kitchen_status.priority = priority
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Order priority set to {priority}'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# Register blueprint in app.py:
# app.register_blueprint(kitchen_orders_bp)