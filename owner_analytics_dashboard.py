# NEW FEATURE: Owner Analytics Dashboard
# Add to app.py - DO NOT modify existing code

from flask import Blueprint, jsonify, request
from sqlalchemy import func, extract
from datetime import datetime, timedelta, date
from models import db, Order, OrderItem, MenuItem, User

owner_analytics_bp = Blueprint('owner_analytics', __name__, url_prefix='/api/owner/analytics')

@owner_analytics_bp.route('/revenue', methods=['GET'])
def get_revenue_analytics():
    """Get revenue trends and analytics"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        period = request.args.get('period', 'month')  # day, week, month, year
        
        if period == 'day':
            start_date = datetime.utcnow().date()
            group_by = func.extract('hour', Order.created_at)
        elif period == 'week':
            start_date = datetime.utcnow().date() - timedelta(days=7)
            group_by = func.date(Order.created_at)
        elif period == 'month':
            start_date = datetime.utcnow().date() - timedelta(days=30)
            group_by = func.date(Order.created_at)
        else:  # year
            start_date = datetime.utcnow().date() - timedelta(days=365)
            group_by = func.extract('month', Order.created_at)
        
        # Revenue trends
        revenue_data = db.session.query(
            group_by.label('period'),
            func.sum(Order.total_amount).label('revenue'),
            func.count(Order.id).label('order_count')
        ).filter(
            func.date(Order.created_at) >= start_date,
            Order.status == 'delivered'
        ).group_by(group_by).all()
        
        # Total revenue
        total_revenue = db.session.query(
            func.sum(Order.total_amount)
        ).filter(
            func.date(Order.created_at) >= start_date,
            Order.status == 'delivered'
        ).scalar() or 0
        
        # Average order value
        avg_order_value = db.session.query(
            func.avg(Order.total_amount)
        ).filter(
            func.date(Order.created_at) >= start_date,
            Order.status == 'delivered'
        ).scalar() or 0
        
        return jsonify({
            'total_revenue': float(total_revenue),
            'avg_order_value': float(avg_order_value),
            'revenue_trend': [{
                'period': str(r.period),
                'revenue': float(r.revenue),
                'orders': int(r.order_count)
            } for r in revenue_data]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@owner_analytics_bp.route('/profit-margin', methods=['GET'])
def get_profit_margin():
    """Calculate profit margins"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        # This is a simplified version - you'd need actual cost data
        period = request.args.get('period', 'month')
        
        if period == 'month':
            start_date = datetime.utcnow().date() - timedelta(days=30)
        else:
            start_date = datetime.utcnow().date() - timedelta(days=7)
        
        total_revenue = db.session.query(
            func.sum(Order.total_amount)
        ).filter(
            func.date(Order.created_at) >= start_date,
            Order.status == 'delivered'
        ).scalar() or 0
        
        # Estimate costs at 40% of revenue (adjust based on your actual costs)
        estimated_costs = total_revenue * 0.4
        profit = total_revenue - estimated_costs
        profit_margin = (profit / total_revenue * 100) if total_revenue > 0 else 0
        
        return jsonify({
            'total_revenue': float(total_revenue),
            'estimated_costs': float(estimated_costs),
            'profit': float(profit),
            'profit_margin_percent': round(profit_margin, 2)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@owner_analytics_bp.route('/customer-patterns', methods=['GET'])
def get_customer_patterns():
    """Analyze customer ordering patterns"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Peak hours
        peak_hours = db.session.query(
            func.extract('hour', Order.created_at).label('hour'),
            func.count(Order.id).label('order_count')
        ).group_by('hour').order_by(func.count(Order.id).desc()).all()
        
        # Orders by day of week
        orders_by_day = db.session.query(
            func.extract('dow', Order.created_at).label('day'),
            func.count(Order.id).label('order_count')
        ).group_by('day').all()
        
        days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        
        return jsonify({
            'peak_hours': [{
                'hour': int(h.hour),
                'orders': int(h.order_count)
            } for h in peak_hours[:5]],
            'orders_by_day': [{
                'day': days[int(d.day)],
                'orders': int(d.order_count)
            } for d in orders_by_day]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@owner_analytics_bp.route('/popular-items', methods=['GET'])
def get_popular_items():
    """Get most and least popular items"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        period = request.args.get('period', 'month')
        
        if period == 'month':
            start_date = datetime.utcnow().date() - timedelta(days=30)
        else:
            start_date = datetime.utcnow().date() - timedelta(days=7)
        
        # Top selling items
        top_items = db.session.query(
            MenuItem.name,
            MenuItem.icon,
            MenuItem.price,
            func.sum(OrderItem.quantity).label('total_sold'),
            func.sum(OrderItem.quantity * OrderItem.price).label('revenue')
        ).join(OrderItem).join(Order).filter(
            func.date(Order.created_at) >= start_date
        ).group_by(MenuItem.id).order_by(
            func.sum(OrderItem.quantity).desc()
        ).limit(10).all()
        
        # Low selling items
        low_items = db.session.query(
            MenuItem.name,
            MenuItem.icon,
            func.sum(OrderItem.quantity).label('total_sold')
        ).join(OrderItem).join(Order).filter(
            func.date(Order.created_at) >= start_date
        ).group_by(MenuItem.id).order_by(
            func.sum(OrderItem.quantity).asc()
        ).limit(5).all()
        
        return jsonify({
            'top_sellers': [{
                'name': item.name,
                'icon': item.icon,
                'quantity_sold': int(item.total_sold),
                'revenue': float(item.revenue)
            } for item in top_items],
            'low_sellers': [{
                'name': item.name,
                'icon': item.icon,
                'quantity_sold': int(item.total_sold)
            } for item in low_items]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@owner_analytics_bp.route('/payment-methods', methods=['GET'])
def get_payment_analytics():
    """Analyze revenue by payment method"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Group by transaction_id prefix to identify payment type
        # This is simplified - you may want a dedicated payment_method field
        
        period = request.args.get('period', 'month')
        
        if period == 'month':
            start_date = datetime.utcnow().date() - timedelta(days=30)
        else:
            start_date = datetime.utcnow().date() - timedelta(days=7)
        
        orders = Order.query.filter(
            func.date(Order.created_at) >= start_date,
            Order.status == 'delivered'
        ).all()
        
        payment_summary = {
            'UPI': {'count': 0, 'amount': 0},
            'Card': {'count': 0, 'amount': 0},
            'Cash': {'count': 0, 'amount': 0},
            'Other': {'count': 0, 'amount': 0}
        }
        
        for order in orders:
            txn_id = (order.transaction_id or '').upper()
            if 'UPI' in txn_id or 'GPay' in txn_id or 'PhonePe' in txn_id:
                payment_summary['UPI']['count'] += 1
                payment_summary['UPI']['amount'] += order.total_amount
            elif 'CARD' in txn_id or 'VISA' in txn_id or 'MASTER' in txn_id:
                payment_summary['Card']['count'] += 1
                payment_summary['Card']['amount'] += order.total_amount
            elif 'CASH' in txn_id:
                payment_summary['Cash']['count'] += 1
                payment_summary['Cash']['amount'] += order.total_amount
            else:
                payment_summary['Other']['count'] += 1
                payment_summary['Other']['amount'] += order.total_amount
        
        return jsonify(payment_summary), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Register blueprint in app.py:
# app.register_blueprint(owner_analytics_bp)