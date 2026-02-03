# NEW FEATURE: Financial Reports for Owner
# Add to app.py - DO NOT modify existing code

from flask import Blueprint, jsonify, request, send_file
from sqlalchemy import func
from datetime import datetime, timedelta, date
from io import BytesIO
import csv
from models import db, Order, OrderItem, MenuItem
# DO NOT import get_auth_user at module level

financial_reports_bp = Blueprint('financial_reports', __name__, url_prefix='/api/owner/reports')

@financial_reports_bp.route('/sales-summary', methods=['GET'])
def get_sales_summary():
    """Get sales summary report"""
    from app import get_auth_user
    try:
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        period = request.args.get('period', 'month')
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        
        if start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        elif period == 'today':
            start_date = end_date = date.today()
        elif period == 'week':
            end_date = date.today()
            start_date = end_date - timedelta(days=7)
        else:  # month
            end_date = date.today()
            start_date = end_date - timedelta(days=30)
        
        # Total sales
        total_sales = db.session.query(
            func.sum(Order.total_amount)
        ).filter(
            func.date(Order.created_at) >= start_date,
            func.date(Order.created_at) <= end_date,
            Order.status == 'delivered'
        ).scalar() or 0
        
        # Number of orders
        order_count = Order.query.filter(
            func.date(Order.created_at) >= start_date,
            func.date(Order.created_at) <= end_date,
            Order.status == 'delivered'
        ).count()
        
        # Average order value
        avg_order = total_sales / order_count if order_count > 0 else 0
        
        # Sales by category
        category_sales = db.session.query(
            MenuItem.category,
            func.sum(OrderItem.quantity * OrderItem.price).label('revenue')
        ).join(OrderItem).join(Order).filter(
            func.date(Order.created_at) >= start_date,
            func.date(Order.created_at) <= end_date
        ).group_by(MenuItem.category).all()
        
        return jsonify({
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'summary': {
                'total_sales': float(total_sales),
                'order_count': order_count,
                'avg_order_value': float(avg_order)
            },
            'category_breakdown': [{
                'category': c.category,
                'revenue': float(c.revenue)
            } for c in category_sales]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@financial_reports_bp.route('/daily-report', methods=['GET'])
def get_daily_report():
    """Get detailed daily sales report"""
    from app import get_auth_user
    try:
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401

        report_date_str = request.args.get('date', date.today().isoformat())
        report_date = datetime.strptime(report_date_str, '%Y-%m-%d').date()
        # Orders for the day
        orders = Order.query.filter(
            func.date(Order.created_at) == report_date
        ).all()

        order_list = []
        total = 0
        for o in orders:
            total += o.total_amount
            order_list.append({
                'id': o.order_id,
                'customer': o.customer_name,
                'total': o.total_amount,
                'status': o.status,
                'created_at': o.created_at.isoformat()
            })
        return jsonify({
            'date': report_date.isoformat(),
            'orders': order_list,
            'total_sales': float(total),
            'order_count': len(orders)
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500