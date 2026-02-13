# NEW FEATURE: Kitchen Analytics Dashboard
# Add to app.py - DO NOT modify existing code

from flask import Blueprint, jsonify, request
from sqlalchemy import func
from datetime import datetime, timedelta, date
from models import db, Order, OrderItem, MenuItem, KitchenOrderStatus
# DO NOT import get_auth_user at module level

kitchen_analytics_bp = Blueprint('kitchen_analytics', __name__, url_prefix='/api/kitchen/analytics')

@kitchen_analytics_bp.route('/today-summary', methods=['GET'])
def get_today_summary():
    """Get today's kitchen performance summary"""
    from app import get_auth_user
    try:
        user = get_auth_user()
        if not user or user.role not in ['kitchen', 'owner']:
            return jsonify({'error': 'Unauthorized'}), 401
        
        today = date.today()
        
        # Orders completed today
        completed_today = Order.query.filter(
            func.date(Order.created_at) == today,
            Order.status == 'delivered'
        ).count()
        
        # Average preparation time
        statuses = KitchenOrderStatus.query.filter(
            KitchenOrderStatus.preparation_completed_at.isnot(None),
            KitchenOrderStatus.preparation_started_at.isnot(None),
            func.date(KitchenOrderStatus.preparation_started_at) == today
        ).all()
        
        if statuses:
            total_time = sum([
                (s.preparation_completed_at - s.preparation_started_at).total_seconds() / 60
                for s in statuses
            ])
            avg_prep_time = round(total_time / len(statuses), 1)
        else:
            avg_prep_time = 0
        
        # Peak hours
        orders_by_hour = db.session.query(
            func.extract('hour', Order.created_at).label('hour'),
            func.count(Order.id).label('count')
        ).filter(
            func.date(Order.created_at) == today
        ).group_by('hour').all()
        
        peak_hour = max(orders_by_hour, key=lambda x: x.count).hour if orders_by_hour else 12
        
        # Most ordered items today
        top_items = db.session.query(
            MenuItem.name,
            MenuItem.icon,
            func.sum(OrderItem.quantity).label('total')
        ).join(OrderItem).join(Order).filter(
            func.date(Order.created_at) == today
        ).group_by(MenuItem.id).order_by(func.sum(OrderItem.quantity).desc()).limit(5).all()
        
        return jsonify({
            'completed_orders': completed_today,
            'avg_preparation_time': avg_prep_time,
            'peak_hour': int(peak_hour),
            'top_items': [{
                'name': item.name,
                'icon': item.icon,
                'quantity': int(item.total)
            } for item in top_items]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@kitchen_analytics_bp.route('/performance', methods=['GET'])
def get_performance_metrics():
    """Get kitchen performance metrics"""
    from app import get_auth_user
    try:
        user = get_auth_user()
        if not user or user.role not in ['kitchen', 'owner']:
            return jsonify({'error': 'Unauthorized'}), 401
        
        period = request.args.get('period', 'week')  # day, week, month
        
        if period == 'day':
            start_date = datetime.utcnow().date()
        elif period == 'week':
            start_date = datetime.utcnow().date() - timedelta(days=7)
        else:  # month
            start_date = datetime.utcnow().date() - timedelta(days=30)
        
        # Orders per hour trend
        orders_per_hour = db.session.query(
            func.extract('hour', Order.created_at).label('hour'),
            func.count(Order.id).label('count')
        ).filter(
            func.date(Order.created_at) >= start_date
        ).group_by('hour').all()
        
        return jsonify({
            'orders_per_hour': [{
                'hour': int(o.hour),
                'count': int(o.count)
            } for o in orders_per_hour]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Register blueprint in app.py:
# app.register_blueprint(kitchen_analytics_bp)