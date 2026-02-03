from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

# --- Models (move all from app.py here) ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(10), unique=True, nullable=False)
    college_id = db.Column(db.String(50), unique=True, nullable=True)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='customer')
    department = db.Column(db.String(100))
    year = db.Column(db.String(20))
    address = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_vip = db.Column(db.Boolean, default=False)
    is_blocked = db.Column(db.Boolean, default=False)
    wallet_balance = db.Column(db.Float, default=0.0)  # Wallet balance for refunds
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'role': self.role,
            'phone': self.phone,
            'college_id': self.college_id,
            'department': self.department,
            'year': self.year,
            'address': self.address,
            'is_vip': self.is_vip,
            'wallet_balance': self.wallet_balance
        }

class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(10), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    available = db.Column(db.Boolean, default=True)
    tags = db.Column(db.String(200))
    image_url = db.Column(db.String(500), nullable=True)  # Image URL for menu items

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.String(50), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(10), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    transaction_id = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='orders')
    kitchen_status = db.Column(db.String(20), default='pending', nullable=True)
    preparation_started_at = db.Column(db.DateTime, nullable=True)
    preparation_completed_at = db.Column(db.DateTime, nullable=True)
    kitchen_notes = db.Column(db.String(500), nullable=True)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    order = db.relationship('Order', backref='items')
    menu_item = db.relationship('MenuItem', backref='order_items')

class Coupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    coupon_id = db.Column(db.String(50), unique=True, nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    qr_data = db.Column(db.String(500), nullable=False)
    expired = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='pending')
    expired_by = db.Column(db.String(50))
    expired_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    order = db.relationship('Order', backref='coupons')

class PromoCode(db.Model):
    __tablename__ = 'promo_code'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    discount_percent = db.Column(db.Float, default=0)
    max_discount = db.Column(db.Float, default=0)
    min_order_value = db.Column(db.Float, default=0)
    expiry_date = db.Column(db.DateTime, nullable=True)
    usage_count = db.Column(db.Integer, default=0)
    active = db.Column(db.Boolean, default=True)

class StaffMember(db.Model):
    __tablename__ = 'staff_member'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    shift_start = db.Column(db.DateTime, nullable=True)
    shift_end = db.Column(db.DateTime, nullable=True)
    orders_handled = db.Column(db.Integer, default=0)

class Settings(db.Model):
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.String(500), nullable=False)

class Inventory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    unit = db.Column(db.String(30))
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'))
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    contact = db.Column(db.String(100))
    email = db.Column(db.String(120))
    address = db.Column(db.String(200))
    inventory = db.relationship('Inventory', backref='supplier')

class SystemSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False)
    value = db.Column(db.String(255))

class Promotion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    promo_type = db.Column(db.String(50))

class InventoryItem(db.Model):
    __tablename__ = 'inventory_item'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50))  # vegetables, dairy, spices, etc.
    quantity = db.Column(db.Float, default=0)
    unit = db.Column(db.String(20))  # kg, ltr, pcs, etc.
    low_stock_threshold = db.Column(db.Float, default=10)
    reorder_quantity = db.Column(db.Float, default=50)
    cost_per_unit = db.Column(db.Float)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.String(100))
    transactions = db.relationship('InventoryTransaction', backref='inventory_item')

class InventoryTransaction(db.Model):
    __tablename__ = 'inventory_transaction'
    id = db.Column(db.Integer, primary_key=True)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey('inventory_item.id'), nullable=False)
    transaction_type = db.Column(db.String(20))  # purchase, usage, wastage, adjustment
    quantity = db.Column(db.Float)
    notes = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(100))

class KitchenOrderStatus(db.Model):
    __tablename__ = 'kitchen_order_status'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False, unique=True)
    status = db.Column(db.String(20), default='pending')  # pending, in_progress, ready, completed
    priority = db.Column(db.String(10), default='regular')  # regular, urgent
    assigned_staff = db.Column(db.String(100))
    preparation_started_at = db.Column(db.DateTime)
    preparation_completed_at = db.Column(db.DateTime)
    estimated_time = db.Column(db.Integer)  # in minutes
    notes = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    order = db.relationship('Order', backref='kitchen_entries')

class StaffPerformance(db.Model):
    __tablename__ = 'staff_performance'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, default=datetime.utcnow)
    orders_completed = db.Column(db.Integer, default=0)
    avg_preparation_time = db.Column(db.Float)
    shift_start = db.Column(db.DateTime)
    shift_end = db.Column(db.DateTime)
    user = db.relationship('User', backref='performance')

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    user = db.relationship('User', backref='notifications')

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    rating = db.Column(db.Integer, nullable=True)
    message = db.Column(db.String(1000), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='feedback')

class Combo(db.Model):
    __tablename__ = 'combo'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500))
    price = db.Column(db.Float, nullable=False)
    icon = db.Column(db.String(10), default='🍱')
    available = db.Column(db.Boolean, default=True)
    image_url = db.Column(db.String(500), nullable=True)  # Image URL for combos
    items = db.relationship('ComboItem', backref='combo', cascade='all, delete-orphan')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ComboItem(db.Model):
    __tablename__ = 'combo_item'
    id = db.Column(db.Integer, primary_key=True)
    combo_id = db.Column(db.Integer, db.ForeignKey('combo.id'), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    menu_item = db.relationship('MenuItem', backref='combo_items')

class Offer(db.Model):
    __tablename__ = 'offer'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500))
    discount_percent = db.Column(db.Float, nullable=False)  # e.g., 20 for 20%
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=True)  # NULL means no expiry
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

class DailyOrderLog(db.Model):
    __tablename__ = 'daily_order_log'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.String(50), nullable=False)
    order_db_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    customer_name = db.Column(db.String(100))
    customer_phone = db.Column(db.String(10))
    customer_email = db.Column(db.String(120))
    order_date = db.Column(db.Date, nullable=False)
    order_time = db.Column(db.DateTime, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    transaction_id = db.Column(db.String(100))
    payment_method = db.Column(db.String(20))  # online, cash, offline
    status = db.Column(db.String(20))
    items_json = db.Column(db.Text)  # JSON string of all items
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    order = db.relationship('Order', backref='daily_logs')