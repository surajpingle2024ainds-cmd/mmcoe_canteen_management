# NEW FEATURE: Customer Management for Owner
# Add to app.py - DO NOT modify existing code

from flask import Blueprint, jsonify, request
from sqlalchemy import func, desc
from datetime import datetime, timedelta
from models import db, User, MenuItem, Order, OrderItem
# DO NOT import get_auth_user at the module level
# Remove CustomerLoyalty model definition from here - define only in models.py

customer_management_bp = Blueprint('customer_management', __name__, url_prefix='/api/owner/customers')

# New Model for Customer Loyalty
# class CustomerLoyalty(db.Model):
#     __tablename__ = 'customer_loyalty'
#     id = db.Column(db.Integer, primary_key=True)
#     user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
#     points = db.Column(db.Integer, default=0)
#     tier = db.Column(db.String(20), default='Bronze')  # Bronze, Silver, Gold, Platinum
#     total_spent = db.Column(db.Float, default=0)
#     total_orders = db.Column(db.Integer, default=0)
#     last_order_date = db.Column(db.DateTime)
    
#     user = db.relationship('User', backref='loyalty')

@customer_management_bp.route('/list', methods=['GET'])
def get_all_customers():
    """Get list of all customers"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        customers = User.query.filter_by(role='customer').all()
        
        result = []
        for customer in customers:
            # Get customer stats
            total_orders = Order.query.filter_by(user_id=customer.id).count()
            total_spent = db.session.query(
                func.sum(Order.total_amount)
            ).filter_by(user_id=customer.id).scalar() or 0
            
            last_order = Order.query.filter_by(
                user_id=customer.id
            ).order_by(desc(Order.created_at)).first()
            
            result.append({
                'id': customer.id,
                'name': customer.name,
                'email': customer.email,
                'phone': customer.phone,
                'college_id': customer.college_id,
                'department': customer.department,
                'total_orders': total_orders,
                'total_spent': float(total_spent),
                'last_order': last_order.created_at.isoformat() if last_order else None,
                'member_since': customer.created_at.isoformat()
            })
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@customer_management_bp.route('/<int:customer_id>', methods=['GET'])
def get_customer_details(customer_id):
    """Get detailed information about a specific customer"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        customer = User.query.get(customer_id)
        if not customer:
            return jsonify({'error': 'Customer not found'}), 404
        
        # Order history
        orders = Order.query.filter_by(user_id=customer_id).order_by(
            desc(Order.created_at)
        ).limit(10).all()
        
        # Favorite items
        favorite_items = db.session.query(
            MenuItem.name,
            MenuItem.icon,
            func.sum(OrderItem.quantity).label('total_ordered')
        ).join(OrderItem).join(Order).filter(
            Order.user_id == customer_id
        ).group_by(MenuItem.id).order_by(
            desc('total_ordered')
        ).limit(5).all()
        
        # Total spent
        total_spent = db.session.query(
            func.sum(Order.total_amount)
        ).filter_by(user_id=customer_id).scalar() or 0
        
        return jsonify({
            'customer': {
                'id': customer.id,
                'name': customer.name,
                'email': customer.email,
                'phone': customer.phone,
                'college_id': customer.college_id,
                'department': customer.department,
                'year': customer.year
            },
            'stats': {
                'total_orders': len(orders),
                'total_spent': float(total_spent),
                'avg_order_value': float(total_spent / len(orders)) if orders else 0
            },
            'recent_orders': [{
                'order_id': o.order_id,
                'total': o.total_amount,
                'date': o.created_at.isoformat(),
                'status': o.status
            } for o in orders],
            'favorite_items': [{
                'name': item.name,
                'icon': item.icon,
                'times_ordered': int(item.total_ordered)
            } for item in favorite_items]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@customer_management_bp.route('/top-customers', methods=['GET'])
def get_top_customers():
    """Get top customers by spending"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        limit = int(request.args.get('limit', 10))
        
        top_customers = db.session.query(
            User.id,
            User.name,
            User.email,
            func.sum(Order.total_amount).label('total_spent'),
            func.count(Order.id).label('order_count')
        ).join(Order).filter(
            User.role == 'customer'
        ).group_by(User.id).order_by(
            desc('total_spent')
        ).limit(limit).all()
        
        return jsonify([{
            'id': c.id,
            'name': c.name,
            'email': c.email,
            'total_spent': float(c.total_spent),
            'order_count': int(c.order_count)
        } for c in top_customers]), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@customer_management_bp.route('/loyalty/<int:customer_id>', methods=['GET', 'POST'])
def manage_loyalty_points(customer_id):
    """Get or update customer loyalty points"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        if request.method == 'GET':
            from models import CustomerLoyalty
            loyalty = CustomerLoyalty.query.filter_by(user_id=customer_id).first()
            
            if not loyalty:
                return jsonify({
                    'points': 0,
                    'tier': 'Bronze',
                    'total_spent': 0,
                    'total_orders': 0
                }), 200
            
            return jsonify({
                'points': loyalty.points,
                'tier': loyalty.tier,
                'total_spent': loyalty.total_spent,
                'total_orders': loyalty.total_orders,
                'last_order_date': loyalty.last_order_date.isoformat() if loyalty.last_order_date else None
            }), 200
        
        else:  # POST - Update points
            data = request.get_json()
            points_to_add = int(data.get('points', 0))
            
            from models import CustomerLoyalty
            loyalty = CustomerLoyalty.query.filter_by(user_id=customer_id).first()
            
            if not loyalty:
                loyalty = CustomerLoyalty(user_id=customer_id)
                db.session.add(loyalty)
            
            loyalty.points += points_to_add
            
            # Update tier based on total spent
            if loyalty.total_spent >= 10000:
                loyalty.tier = 'Platinum'
            elif loyalty.total_spent >= 5000:
                loyalty.tier = 'Gold'
            elif loyalty.total_spent >= 2000:
                loyalty.tier = 'Silver'
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'new_points': loyalty.points,
                'tier': loyalty.tier
            }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@customer_management_bp.route('/feedback', methods=['GET'])
def get_customer_feedback():
    """Get customer feedback and ratings (placeholder)"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        # This would require a Feedback model - placeholder for now
        return jsonify({
            'message': 'Feedback feature coming soon',
            'avg_rating': 4.5,
            'total_reviews': 0
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Register blueprint in app.py:
# app.register_blueprint(customer_management_bp)