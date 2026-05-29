# NEW FEATURE: Kitchen Analytics Dashboard
# Add to app.py - DO NOT modify existing code

from flask import Blueprint, jsonify, request
from sqlalchemy import func
from datetime import datetime, timedelta, date
from models import db, Order, OrderItem, MenuItem
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

        # Average preparation time (minutes) — using preparation_started/completed columns if available
        avg_cook_minutes = None
        try:
            statuses = Order.query.filter(
                func.date(Order.created_at) == today,
                Order.preparation_started_at.isnot(None),
                Order.preparation_completed_at.isnot(None),
            ).all()
            if statuses:
                total_secs = sum(
                    (o.preparation_completed_at - o.preparation_started_at).total_seconds()
                    for o in statuses
                )
                avg_cook_minutes = round(total_secs / len(statuses) / 60, 1)
        except Exception:
            # Fallback: estimate from accepted→ready timing via status column
            try:
                ready_orders = Order.query.filter(
                    func.date(Order.created_at) == today,
                    Order.status.in_(['ready', 'delivered'])
                ).all()
                if ready_orders:
                    diffs = []
                    for o in ready_orders:
                        if o.created_at:
                            diff = (datetime.utcnow() - o.created_at).total_seconds() / 60
                            if 0 < diff < 120:   # sanity check: < 2h
                                diffs.append(diff)
                    if diffs:
                        avg_cook_minutes = round(sum(diffs) / len(diffs), 1)
            except Exception:
                pass

        # Hourly order counts across the operating day (8 AM – 6 PM)
        orders_by_hour_raw = db.session.query(
            func.extract('hour', Order.created_at).label('hour'),
            func.count(Order.id).label('count')
        ).filter(
            func.date(Order.created_at) == today
        ).group_by(func.extract('hour', Order.created_at)).all()

        hour_map = {int(r.hour): int(r.count) for r in orders_by_hour_raw}
        now_hour = datetime.utcnow().hour
        # Show 8 AM through end of current hour (or 6 PM, whichever is earlier)
        end_hour = min(max(now_hour + 1, 14), 19)
        hourly_counts = [
            {'hour': h, 'count': hour_map.get(h, 0)}
            for h in range(8, end_hour)
        ]

        # Peak hour
        peak_hour = max(hour_map, key=hour_map.get) if hour_map else now_hour

        # Top items today
        top_items = db.session.query(
            MenuItem.name,
            MenuItem.icon,
            func.sum(OrderItem.quantity).label('total')
        ).join(OrderItem).join(Order).filter(
            func.date(Order.created_at) == today
        ).group_by(MenuItem.id).order_by(func.sum(OrderItem.quantity).desc()).limit(5).all()

        return jsonify({
            'completed_orders': completed_today,
            'avg_cook_minutes': avg_cook_minutes,        # used by JS
            'avg_preparation_time': avg_cook_minutes,    # legacy alias
            'peak_hour': int(peak_hour),
            'hourly_counts': hourly_counts,              # used by bar chart JS
            'top_items': [
                {'name': item.name, 'icon': item.icon, 'quantity': int(item.total)}
                for item in top_items
            ]
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