# NEW FEATURE: Staff Management for Owner
# Add to app.py - DO NOT modify existing code

from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta, date
from models import db, User, StaffPerformance, KitchenOrderStatus
from werkzeug.security import generate_password_hash
from sqlalchemy import func
# DO NOT import get_auth_user at module level

staff_management_bp = Blueprint('staff_management', __name__, url_prefix='/api/owner/staff')

@staff_management_bp.route('/list', methods=['GET'])
def get_all_staff():
    """Get list of all staff members"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        staff_members = User.query.filter(
            User.role.in_(['kitchen', 'staff'])
        ).all()
        
        result = []
        for member in staff_members:
            # Get performance stats
            total_orders = db.session.query(
                func.sum(StaffPerformance.orders_completed)
            ).filter_by(user_id=member.id).scalar() or 0
            
            # Get recent performance
            recent_performance = StaffPerformance.query.filter_by(
                user_id=member.id
            ).order_by(StaffPerformance.date.desc()).first()
            
            result.append({
                'id': member.id,
                'name': member.name,
                'email': member.email,
                'phone': member.phone,
                'college_id': member.college_id,
                'role': member.role,
                'department': member.department,
                'total_orders_completed': int(total_orders),
                'last_shift': recent_performance.date.isoformat() if recent_performance else None,
                'avg_prep_time': recent_performance.avg_preparation_time if recent_performance else None,
                'created_at': member.created_at.isoformat(),
                'is_blocked': getattr(member, 'is_blocked', False)
            })
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@staff_management_bp.route('/add', methods=['POST'])
def add_staff_member():
    """Add new staff member"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        
        # Validation
        required = ['name', 'email', 'phone', 'college_id', 'password']
        missing = [f for f in required if not data.get(f)]
        
        if missing:
            return jsonify({'error': f'Missing fields: {", ".join(missing)}'}), 400
        
        # Check if email or college_id already exists
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'error': 'Email already registered'}), 400
        
        if User.query.filter_by(college_id=data['college_id']).first():
            return jsonify({'error': 'College ID already registered'}), 400
        
        # Create staff member
        new_staff = User(
            name=data['name'].strip(),
            email=data['email'].strip().lower(),
            phone=data['phone'].strip(),
            college_id=data['college_id'].strip(),
            password=generate_password_hash(data['password']),
            role=data.get('role', 'kitchen'),  # kitchen or staff
            department=data.get('department', 'Kitchen'),
            year='Staff'
        )
        
        db.session.add(new_staff)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Staff member {new_staff.name} added successfully',
            'staff_id': new_staff.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@staff_management_bp.route('/<int:staff_id>', methods=['PUT'])
def update_staff_member(staff_id):
    """Update staff member details"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        staff = User.query.get(staff_id)
        
        if not staff or staff.role not in ['kitchen', 'staff']:
            return jsonify({'error': 'Staff member not found'}), 404
        
        # Update fields
        if 'name' in data:
            staff.name = data['name']
        if 'email' in data:
            staff.email = data['email']
        if 'phone' in data:
            staff.phone = data['phone']
        if 'department' in data:
            staff.department = data['department']
        if 'password' in data and data['password']:
            staff.password = generate_password_hash(data['password'])
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Staff member updated successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@staff_management_bp.route('/<int:staff_id>/block', methods=['PUT'])
def block_staff_member(staff_id):
    """Block/Unblock staff member"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        staff = User.query.get(staff_id)
        
        if not staff or staff.role not in ['kitchen', 'staff']:
            return jsonify({'error': 'Staff member not found'}), 404
        
        # Toggle block status
        staff.is_blocked = not getattr(staff, 'is_blocked', False)
        
        db.session.commit()
        
        status = 'blocked' if staff.is_blocked else 'unblocked'
        
        return jsonify({
            'success': True,
            'message': f'Staff member {status} successfully',
            'is_blocked': staff.is_blocked
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@staff_management_bp.route('/<int:staff_id>/delete', methods=['DELETE'])
def delete_staff_member(staff_id):
    """Delete staff member (soft delete by blocking)"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        staff = User.query.get(staff_id)
        
        if not staff or staff.role not in ['kitchen', 'staff']:
            return jsonify({'error': 'Staff member not found'}), 404
        
        # Soft delete by blocking
        staff.is_blocked = True
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Staff member removed successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@staff_management_bp.route('/performance-report', methods=['GET'])
def get_performance_report():
    """Get comprehensive staff performance report"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        period = request.args.get('period', 'month')
        
        if period == 'week':
            start_date = date.today() - timedelta(days=7)
        else:  # month
            start_date = date.today() - timedelta(days=30)
        
        # Get all staff performance data
        performance_data = db.session.query(
            User.id,
            User.name,
            func.sum(StaffPerformance.orders_completed).label('total_orders'),
            func.avg(StaffPerformance.avg_preparation_time).label('avg_prep_time'),
            func.count(StaffPerformance.id).label('days_worked')
        ).join(
            StaffPerformance, User.id == StaffPerformance.user_id
        ).filter(
            User.role.in_(['kitchen', 'staff']),
            StaffPerformance.date >= start_date
        ).group_by(User.id).all()
        
        result = [{
            'staff_id': p.id,
            'staff_name': p.name,
            'total_orders': int(p.total_orders or 0),
            'avg_prep_time': round(float(p.avg_prep_time or 0), 2),
            'days_worked': int(p.days_worked),
            'orders_per_day': round(float(p.total_orders or 0) / max(int(p.days_worked), 1), 2)
        } for p in performance_data]
        
        # Sort by total orders
        result.sort(key=lambda x: x['total_orders'], reverse=True)
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@staff_management_bp.route('/attendance', methods=['GET'])
def get_staff_attendance():
    """Get staff attendance records"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        date_param = request.args.get('date', date.today().isoformat())
        target_date = datetime.strptime(date_param, '%Y-%m-%d').date()
        
        # Get all staff
        staff_members = User.query.filter(
            User.role.in_(['kitchen', 'staff'])
        ).all()
        
        result = []
        
        for staff in staff_members:
            attendance = StaffPerformance.query.filter_by(
                user_id=staff.id,
                date=target_date
            ).first()
            
            result.append({
                'staff_id': staff.id,
                'staff_name': staff.name,
                'date': target_date.isoformat(),
                'clocked_in': attendance is not None and attendance.shift_start is not None,
                'shift_start': attendance.shift_start.isoformat() if attendance and attendance.shift_start else None,
                'shift_end': attendance.shift_end.isoformat() if attendance and attendance.shift_end else None,
                'hours_worked': ((attendance.shift_end - attendance.shift_start).total_seconds() / 3600) if attendance and attendance.shift_end and attendance.shift_start else 0,
                'orders_completed': attendance.orders_completed if attendance else 0
            })
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@staff_management_bp.route('/schedule', methods=['GET', 'POST'])
def manage_staff_schedule():
    """Get or create staff schedule (placeholder for future enhancement)"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        if request.method == 'GET':
            # Return placeholder schedule
            return jsonify({
                'message': 'Staff scheduling feature coming soon',
                'current_staff_count': User.query.filter(User.role.in_(['kitchen', 'staff'])).count()
            }), 200
        
        else:  # POST
            # Placeholder for creating schedule
            return jsonify({
                'success': True,
                'message': 'Schedule feature in development'
            }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Register blueprint in app.py:
# app.register_blueprint(staff_management_bp)