from flask import Blueprint, request, jsonify, current_app
from models import db, MenuItem
import re

chatbot_bp = Blueprint('chatbot', __name__)

# Get menu items from your existing database
def get_menu_items():
    """Get available menu items from database"""
    try:
        items = MenuItem.query.filter_by(available=True).all()
        return items
    except Exception as e:
        print(f"Error fetching menu items: {e}")
        return []

def process_chatbot_message(message):
    """Process chatbot message and return response"""
    msg = message.lower().strip()
    
    # Greetings
    if re.search(r'\b(hi|hello|hey|good morning|good afternoon)\b', msg):
        return {
            'response': "Hello! 👋 Welcome to our canteen. How can I assist you today?",
            'suggestions': ['Show Menu', 'Popular Items', 'Order Food', 'Help']
        }
    
    # Show menu
    if re.search(r'\b(menu|show menu|items|what do you have)\b', msg):
        items = get_menu_items()
        menu_text = "📋 **Our Menu**\n\n"
        
        categories = {}
        for item in items:
            if item.category not in categories:
                categories[item.category] = []
            categories[item.category].append(item)
        
        for category, items_list in categories.items():
            menu_text += f"\n{category.upper()}\n"
            for item in items_list:
                icon = getattr(item, 'icon', '🍽️')
                menu_text += f"{icon} {item.name} - ₹{item.price}\n"
        
        return {
            'response': menu_text,
            'suggestions': ['Order Now', 'Popular Items']
        }
    
    # Price inquiry
    if re.search(r'\b(price|cost|how much)\b', msg):
        items = get_menu_items()
        for item in items:
            if item.name.lower() in msg:
                icon = getattr(item, 'icon', '🍽️')
                return {
                    'response': f"{icon} {item.name} costs ₹{item.price}",
                    'suggestions': ['Show Menu', 'Order This']
                }
        return {
            'response': "Please specify which item's price you'd like to know.",
            'suggestions': ['Show Menu']
        }
    
    # Order guidance
    if re.search(r'\b(order|want|buy)\b', msg):
        return {
            'response': "To place an order:\n1. Click 'Browse Menu'\n2. Select items\n3. Add to cart\n4. Checkout\n\nShall I show you the menu?",
            'suggestions': ['Show Menu', 'My Cart']
        }
    
    # Help
    if re.search(r'\b(help|assist)\b', msg):
        return {
            'response': "I can help you with:\n• View menu\n• Check prices\n• Place orders\n• Track orders\n\nWhat do you need?",
            'suggestions': ['Show Menu', 'My Orders']
        }
    
    # Default
    return {
        'response': "I can help you browse menu, check prices, or place orders. What would you like?",
        'suggestions': ['Show Menu', 'Help']
    }

@chatbot_bp.route('/api/chatbot/chat', methods=['POST', 'OPTIONS'])
def chat():
    """Chatbot API endpoint"""
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response, 204
    
    try:
        print("Chatbot endpoint called")
        data = request.get_json()
        print(f"Received data: {data}")
        
        if not data or 'message' not in data:
            return jsonify({'error': 'Message required'}), 400
        
        message = data.get('message', '').strip()
        if not message:
            return jsonify({'error': 'Message cannot be empty'}), 400
        
        print(f"Processing message: {message}")
        result = process_chatbot_message(message)
        print(f"Result: {result}")
        return jsonify(result), 200
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"Chatbot error: {error_msg}")
        traceback.print_exc()
        return jsonify({
            'response': f'Sorry, something went wrong: {error_msg}',
            'suggestions': ['Try Again']
        }), 500

@chatbot_bp.route('/api/chatbot/test', methods=['GET'])
def test():
    """Test endpoint to verify chatbot route is working"""
    try:
        items_count = MenuItem.query.count()
        return jsonify({
            'status': 'Chatbot backend is working!',
            'menu_items_count': items_count,
            'endpoint': '/api/chatbot/chat'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'Error',
            'error': str(e)
        }), 500

