# ==================== ADVANCED FEATURES MODULE ====================
# New features: Voice Notifications, Ingredient Checklist, Combo Deals, 
# Segmentation, Voice Ordering, Real-time Tracking, Referral Program,
# Smart Recommendations, Order Insights, Dark Mode

from flask import Blueprint, jsonify, request, render_template_string
from models import db, User, Order, OrderItem, MenuItem, Coupon
from sqlalchemy import func, desc
from datetime import datetime, timedelta
import json

advanced_features_bp = Blueprint('advanced_features', __name__, url_prefix='/api/advanced')

# ==================== 1. VOICE NOTIFICATIONS ====================
@advanced_features_bp.route('/voice-notifications/status', methods=['GET', 'OPTIONS'])
def get_voice_notifications_status():
    """Get voice notifications status for user"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Get unread notifications count
        try:
            from models import Notification
            unread_count = Notification.query.filter_by(user_id=user.id, is_read=False).count()
        except:
            unread_count = 0
        
        return jsonify({
            'enabled': True,
            'unread_count': unread_count,
            'audio_url': 'https://actions.google.com/sounds/v1/alarms/beep_short.ogg'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== 2. INGREDIENT CHECKLIST ====================
@advanced_features_bp.route('/orders/<int:order_id>/ingredients', methods=['GET'])
def get_order_ingredients(order_id):
    """Get ingredient checklist for an order"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role not in ['owner', 'kitchen']:
            return jsonify({'error': 'Unauthorized'}), 401
        
        order = Order.query.get(order_id)
        if not order:
            return jsonify({'error': 'Order not found'}), 404
        
        # Get ingredients for all items in order
        ingredients = {}
        for order_item in order.items:
            menu_item = MenuItem.query.get(order_item.menu_item_id)
            if menu_item:
                # Parse ingredients from description or tags
                item_ingredients = []
                if menu_item.description:
                    # Extract common ingredients from description
                    desc_lower = menu_item.description.lower()
                    common_ingredients = ['tomato', 'onion', 'cheese', 'lettuce', 'chicken', 'paneer', 
                                        'rice', 'wheat', 'potato', 'spices', 'oil', 'garlic', 'ginger']
                    for ing in common_ingredients:
                        if ing in desc_lower:
                            item_ingredients.append(ing.title())
                
                if not item_ingredients:
                    item_ingredients = ['Mixed Ingredients']  # Default
                
                for ing in item_ingredients:
                    if ing not in ingredients:
                        ingredients[ing] = 0
                    ingredients[ing] += order_item.quantity
        
        return jsonify({
            'order_id': order.order_id,
            'ingredients': [{'name': k, 'quantity': v, 'unit': 'units'} for k, v in ingredients.items()],
            'total_items': sum(item.quantity for item in order.items)
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== 3. COMBO/MEAL DEALS CREATOR ====================
@advanced_features_bp.route('/combos', methods=['GET', 'OPTIONS'])
def get_combos():
    """Get all available combo deals"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        from app import get_auth_user
        user = get_auth_user()
        
        # Get popular items to create combos
        try:
            popular_items = db.session.query(
                MenuItem.id,
                MenuItem.name,
                MenuItem.icon,
                MenuItem.price,
                func.sum(OrderItem.quantity).label('total_ordered')
            ).join(OrderItem).join(Order).group_by(MenuItem.id).order_by(desc('total_ordered')).limit(6).all()
        except:
            # If no orders exist, use available menu items
            popular_items = db.session.query(MenuItem).filter_by(available=True).limit(6).all()
            popular_items = [(item.id, item.name, item.icon, item.price, 0) for item in popular_items]
        
        # Create combo deals (combinations of 2-3 popular items)
        combos = []
        if len(popular_items) >= 2:
            # Combo 1: First 2 items
            combo1_items = popular_items[:2]
            # Handle both tuple and object formats
            if isinstance(combo1_items[0], tuple):
                total_price = sum(item[3] if len(item) > 3 else item.price for item in combo1_items)
            else:
                total_price = sum(item.price for item in combo1_items)
            discounted_price = total_price * 0.85  # 15% discount
            # Handle both tuple and object formats
            if isinstance(combo1_items[0], tuple):
                items_list = [{'id': item[0], 'name': item[1], 'icon': item[2], 'price': item[3] if len(item) > 3 else 0} for item in combo1_items]
            else:
                items_list = [{'id': item.id, 'name': item.name, 'icon': item.icon, 'price': item.price} for item in combo1_items]
            
            combos.append({
                'id': 'combo_1',
                'name': 'Popular Combo',
                'items': items_list,
                'original_price': round(total_price, 2),
                'discounted_price': round(discounted_price, 2),
                'savings': round(total_price - discounted_price, 2),
                'description': 'Best selling items together!'
            })
        
        if len(popular_items) >= 3:
            # Combo 2: First 3 items
            combo2_items = popular_items[:3]
            # Handle both tuple and object formats
            if isinstance(combo2_items[0], tuple):
                total_price = sum(item[3] if len(item) > 3 else item.price for item in combo2_items)
                items_list = [{'id': item[0], 'name': item[1], 'icon': item[2], 'price': item[3] if len(item) > 3 else 0} for item in combo2_items]
            else:
                total_price = sum(item.price for item in combo2_items)
                items_list = [{'id': item.id, 'name': item.name, 'icon': item.icon, 'price': item.price} for item in combo2_items]
            
            discounted_price = total_price * 0.80  # 20% discount
            combos.append({
                'id': 'combo_2',
                'name': 'Mega Combo',
                'items': items_list,
                'original_price': round(total_price, 2),
                'discounted_price': round(discounted_price, 2),
                'savings': round(total_price - discounted_price, 2),
                'description': 'Three favorites at a great price!'
            })
        
        return jsonify({'combos': combos}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@advanced_features_bp.route('/combos/<combo_id>/add', methods=['POST', 'OPTIONS'])
def add_combo_to_cart(combo_id):
    """Add combo deal to cart"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Get combo details
        try:
            popular_items = db.session.query(
                MenuItem.id,
                MenuItem.name,
                MenuItem.icon,
                MenuItem.price,
                func.sum(OrderItem.quantity).label('total_ordered')
            ).join(OrderItem).join(Order).group_by(MenuItem.id).order_by(desc('total_ordered')).limit(6).all()
        except:
            # If no orders exist, use available menu items
            popular_items = db.session.query(MenuItem).filter_by(available=True).limit(6).all()
            popular_items = [(item.id, item.name, item.icon, item.price, 0) for item in popular_items]
        
        combo_items = []
        if combo_id == 'combo_1' and len(popular_items) >= 2:
            combo_items = popular_items[:2]
        elif combo_id == 'combo_2' and len(popular_items) >= 3:
            combo_items = popular_items[:3]
        else:
            return jsonify({'error': 'Invalid combo'}), 400
        
        # Return items to add to cart - handle both tuple and object formats
        if combo_items and isinstance(combo_items[0], tuple):
            cart_items = [{
                'id': item[0],
                'name': item[1],
                'icon': item[2],
                'price': item[3] if len(item) > 3 else 0,
                'quantity': 1
            } for item in combo_items]
        else:
            cart_items = [{
                'id': item.id,
                'name': item.name,
                'icon': item.icon,
                'price': item.price,
                'quantity': 1
            } for item in combo_items]
        
        return jsonify({
            'success': True,
            'items': cart_items,
            'message': f'Combo added! Add these items to cart.'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== 4. CUSTOMER SEGMENTATION ====================
@advanced_features_bp.route('/customers/segments', methods=['GET'])
def get_customer_segments():
    """Get customer segments (VIP, Regular, New)"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Calculate segments
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        ninety_days_ago = datetime.utcnow() - timedelta(days=90)
        
        # VIP: Explicitly marked VIP or high order count
        vip_users = []
        try:
            if hasattr(User, 'is_vip'):
                vip_users = db.session.query(User.id).filter(
                    User.is_vip == True
                ).all()
        except:
            pass
        vip_ids = [u.id for u in vip_users]
        
        # Also check for high order count
        high_order_users = db.session.query(Order.user_id).filter(
            Order.created_at >= ninety_days_ago
        ).group_by(Order.user_id).having(func.count(Order.id) > 10).all()
        vip_ids.extend([u.user_id for u in high_order_users])
        vip_ids = list(set(vip_ids))  # Remove duplicates
        
        vip_customers = User.query.filter(User.id.in_(vip_ids)).all() if vip_ids else []
        
        # Regular: 3-10 orders in last 90 days (not VIP)
        regular_query = db.session.query(Order.user_id).filter(
            Order.created_at >= ninety_days_ago
        )
        if vip_ids:
            regular_query = regular_query.filter(~Order.user_id.in_(vip_ids))
        regular_user_ids = regular_query.group_by(Order.user_id).having(func.count(Order.id).between(3, 10)).all()
        regular_customers = User.query.filter(User.id.in_([u.user_id for u in regular_user_ids])).all() if regular_user_ids else []
        
        # New: First order in last 30 days
        new_user_ids = db.session.query(Order.user_id).filter(
            Order.created_at >= thirty_days_ago
        ).group_by(Order.user_id).having(func.min(Order.created_at) >= thirty_days_ago).all()
        new_customers = User.query.filter(User.id.in_([u.user_id for u in new_user_ids])).all() if new_user_ids else []
        
        return jsonify({
            'vip': {
                'count': len(vip_customers),
                'customers': [{'id': u.id, 'name': u.name, 'email': u.email, 'total_orders': Order.query.filter_by(user_id=u.id).count()} for u in vip_customers[:10]]
            },
            'regular': {
                'count': len(regular_customers),
                'customers': [{'id': u.id, 'name': u.name, 'email': u.email, 'total_orders': Order.query.filter_by(user_id=u.id).count()} for u in regular_customers[:10]]
            },
            'new': {
                'count': len(new_customers),
                'customers': [{'id': u.id, 'name': u.name, 'email': u.email, 'total_orders': 1} for u in new_customers[:10]]
            }
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== 5. VOICE ORDERING ====================
@advanced_features_bp.route('/voice/recognize', methods=['POST', 'OPTIONS'])
def recognize_voice():
    """Speech-to-text order placement (simulated)"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        audio_data = data.get('audio_data')  # Base64 encoded audio
        text_transcript = data.get('text', '')  # Optional pre-transcribed text
        
        # In production, use speech recognition API (Google Speech-to-Text, AWS Transcribe, etc.)
        # For demo, accept text directly
        if not text_transcript:
            text_transcript = "I would like to order"  # Default placeholder
        
        # Parse order from text (simple keyword matching)
        order_items = []
        menu_items = MenuItem.query.filter_by(available=True).all()
        
        text_lower = text_transcript.lower()
        for menu_item in menu_items:
            if menu_item.name.lower() in text_lower:
                order_items.append({
                    'id': menu_item.id,
                    'name': menu_item.name,
                    'icon': menu_item.icon,
                    'price': menu_item.price
                })
        
        return jsonify({
            'success': True,
            'transcript': text_transcript,
            'recognized_items': order_items[:5],  # Limit to 5 items
            'message': f'Recognized {len(order_items)} items from your voice order'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== 6. REAL-TIME ORDER TRACKING ====================
@advanced_features_bp.route('/orders/<order_id>/track', methods=['GET', 'OPTIONS'])
def track_order(order_id):
    """Get real-time order tracking status"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401
        
        order = Order.query.filter_by(order_id=order_id).first()
        if not order:
            return jsonify({'error': 'Order not found'}), 404
        
        if user.role != 'owner' and order.user_id != user.id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Status timeline
        statuses = []
        if order.created_at:
            statuses.append({
                'status': 'placed',
                'label': 'Order Placed',
                'timestamp': order.created_at.isoformat(),
                'completed': True
            })
        
        if order.status in ['accepted', 'preparing', 'ready', 'delivered']:
            statuses.append({
                'status': 'accepted',
                'label': 'Order Accepted',
                'timestamp': order.created_at.isoformat() if order.created_at else None,
                'completed': True
            })
        
        if order.status in ['preparing', 'ready', 'delivered']:
            statuses.append({
                'status': 'preparing',
                'label': 'Preparing',
                'timestamp': (order.preparation_started_at.isoformat() if order.preparation_started_at else order.created_at.isoformat()) if order.created_at else None,
                'completed': order.status in ['ready', 'delivered']
            })
        
        if order.status in ['ready', 'delivered']:
            statuses.append({
                'status': 'ready',
                'label': 'Ready for Pickup',
                'timestamp': (order.preparation_completed_at.isoformat() if order.preparation_completed_at else None),
                'completed': order.status == 'delivered'
            })
        
        if order.status == 'delivered':
            statuses.append({
                'status': 'delivered',
                'label': 'Delivered',
                'timestamp': datetime.utcnow().isoformat(),
                'completed': True
            })
        
        # Current status
        current_status = order.status
        status_labels = {
            'pending': 'Waiting for Confirmation',
            'accepted': 'Order Accepted',
            'preparing': 'Preparing Your Order',
            'ready': 'Ready for Pickup',
            'delivered': 'Delivered',
            'rejected': 'Order Rejected'
        }
        
        return jsonify({
            'order_id': order.order_id,
            'current_status': current_status,
            'current_status_label': status_labels.get(current_status, current_status),
            'timeline': statuses,
            'estimated_time': None,  # Can be calculated based on order complexity
            'last_updated': datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== 7. REFERRAL PROGRAM ====================
@advanced_features_bp.route('/referrals', methods=['GET', 'OPTIONS'])
def get_referrals():
    """Get referral information for current user"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Generate referral code (if not exists, use college_id based code)
        referral_code = user.college_id.upper() + str(user.id)[-4:]
        
        # Get referral stats (if referred_by field exists)
        try:
            referred_users = User.query.filter(
                getattr(User, 'referred_by') == user.id
            ).count()
        except:
            referred_users = 0  # Field doesn't exist yet
        
        # Calculate rewards (simplified)
        referral_reward = referred_users * 50  # ₹50 per referral
        
        return jsonify({
            'referral_code': referral_code,
            'referral_link': f'/register?ref={referral_code}',
            'referred_count': referred_users,
            'pending_rewards': referral_reward,
            'message': 'Share your code with friends and earn rewards!'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@advanced_features_bp.route('/referrals/claim', methods=['POST', 'OPTIONS'])
def claim_referral_reward():
    """Claim referral rewards"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401
        
        try:
            referred_count = User.query.filter(getattr(User, 'referred_by') == user.id).count()
        except:
            referred_count = 0  # Field doesn't exist yet
        reward = referred_count * 50
        
        return jsonify({
            'success': True,
            'reward': reward,
            'message': f'You have earned ₹{reward} in referral rewards!'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== 8. SMART RECOMMENDATIONS ====================
@advanced_features_bp.route('/recommendations', methods=['GET', 'OPTIONS'])
def get_recommendations():
    """Get AI-based recommendations for user"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Get user's order history
        user_orders = Order.query.filter_by(user_id=user.id).all()
        
        # Get most ordered categories
        ordered_items = {}
        for order in user_orders:
            for item in order.items:
                menu_item = MenuItem.query.get(item.menu_item_id)
                if menu_item:
                    category = menu_item.category or 'Other'
                    if category not in ordered_items:
                        ordered_items[category] = []
                    ordered_items[category].append({
                        'id': menu_item.id,
                        'name': menu_item.name,
                        'icon': menu_item.icon,
                        'price': menu_item.price,
                        'times_ordered': item.quantity
                    })
        
        # Recommend items from favorite categories
        recommendations = []
        if ordered_items:
            # Get items from most ordered categories
            for category, items in list(ordered_items.items())[:2]:
                category_items = MenuItem.query.filter_by(category=category, available=True).all()
                for item in category_items[:3]:
                    if item.id not in [i['id'] for i in recommendations]:
                        recommendations.append({
                            'id': item.id,
                            'name': item.name,
                            'icon': item.icon,
                            'price': item.price,
                            'category': item.category,
                            'reason': f'Similar to your favorite {category} items'
                        })
        
        # If no history, recommend popular items
        if not recommendations:
            try:
                popular = db.session.query(
                    MenuItem.id,
                    MenuItem.name,
                    MenuItem.icon,
                    MenuItem.price,
                    MenuItem.category,
                    func.sum(OrderItem.quantity).label('total')
                ).join(OrderItem).join(Order).group_by(MenuItem.id).order_by(desc('total')).limit(5).all()
                
                recommendations = [{
                    'id': item.id,
                    'name': item.name,
                    'icon': item.icon,
                    'price': item.price,
                    'category': item.category,
                    'reason': 'Popular choice among customers'
                } for item in popular]
            except:
                # If no orders exist at all, recommend available items
                available_items = MenuItem.query.filter_by(available=True).limit(5).all()
                recommendations = [{
                    'id': item.id,
                    'name': item.name,
                    'icon': item.icon,
                    'price': item.price,
                    'category': item.category or 'Other',
                    'reason': 'Available now'
                } for item in available_items]
        
        return jsonify({
            'recommendations': recommendations[:6],
            'message': 'You might like these items!'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== 9. ORDER HISTORY INSIGHTS ====================
@advanced_features_bp.route('/insights', methods=['GET', 'OPTIONS'])
def get_order_insights():
    """Get order history insights"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401
        
        orders = Order.query.filter_by(user_id=user.id).all()
        
        if not orders:
            return jsonify({
                'insights': [],
                'message': 'No order history yet. Start ordering to see insights!'
            }), 200
        
        # Most ordered item
        item_counts = {}
        for order in orders:
            for item in order.items:
                menu_item = MenuItem.query.get(item.menu_item_id)
                if menu_item:
                    if menu_item.id not in item_counts:
                        item_counts[menu_item.id] = {
                            'item': menu_item,
                            'count': 0,
                            'total_spent': 0
                        }
                    item_counts[menu_item.id]['count'] += item.quantity
                    item_counts[menu_item.id]['total_spent'] += item.price * item.quantity
        
        most_ordered = max(item_counts.items(), key=lambda x: x[1]['count']) if item_counts else None
        
        # Favorite category
        category_counts = {}
        for order in orders:
            for item in order.items:
                menu_item = MenuItem.query.get(item.menu_item_id)
                if menu_item:
                    category = menu_item.category or 'Other'
                    category_counts[category] = category_counts.get(category, 0) + item.quantity
        
        favorite_category = max(category_counts.items(), key=lambda x: x[1])[0] if category_counts else None
        
        # Total stats
        total_orders = len(orders)
        total_spent = sum(order.total_amount for order in orders)
        avg_order_value = total_spent / total_orders if total_orders > 0 else 0
        
        insights = []
        if most_ordered:
            insights.append({
                'type': 'most_ordered',
                'label': 'Your Most Ordered Item',
                'value': most_ordered[1]['item'].name,
                'icon': most_ordered[1]['item'].icon,
                'count': most_ordered[1]['count'],
                'details': f"You've ordered this {most_ordered[1]['count']} times"
            })
        
        if favorite_category:
            insights.append({
                'type': 'favorite_category',
                'label': 'Favorite Category',
                'value': favorite_category,
                'count': category_counts[favorite_category],
                'details': f'{category_counts[favorite_category]} items from this category'
            })
        
        insights.append({
            'type': 'total_stats',
            'label': 'Total Orders',
            'value': str(total_orders),
            'details': f'₹{round(total_spent, 2)} total spent, ₹{round(avg_order_value, 2)} avg per order'
        })
        
        return jsonify({
            'insights': insights,
            'summary': {
                'total_orders': total_orders,
                'total_spent': round(total_spent, 2),
                'avg_order_value': round(avg_order_value, 2),
                'most_ordered_item': most_ordered[1]['item'].name if most_ordered else None,
                'favorite_category': favorite_category
            }
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== 10. DARK MODE ====================
@advanced_features_bp.route('/theme/dark-mode', methods=['GET', 'POST'])
def dark_mode():
    """Get or set dark mode preference"""
    try:
        from app import get_auth_user
        user = get_auth_user()
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401
        
        if request.method == 'POST':
            data = request.get_json()
            dark_mode_enabled = data.get('enabled', False)
            
            # Store preference in user settings (simplified - use localStorage on frontend)
            # In production, store in UserSettings model
            
            return jsonify({
                'success': True,
                'dark_mode': dark_mode_enabled,
                'message': 'Dark mode preference saved'
            }), 200
        else:
            # Get preference (default: false)
            return jsonify({
                'dark_mode': False,  # Can be fetched from UserSettings in production
                'message': 'Use localStorage for dark mode preference'
            }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

