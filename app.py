from flask import Flask, request, jsonify, send_file, render_template_string, Blueprint, render_template, redirect, make_response
from flask_cors import CORS
from models import db, User, MenuItem, Order, OrderItem, Coupon, PromoCode, StaffMember, Settings, Inventory, Supplier, SystemSetting, Promotion, Combo, ComboItem, Offer, DailyOrderLog
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from datetime import datetime, timedelta, date
import csv
import random
import string
import uuid
from sqlalchemy import func, desc, and_, or_
import os
import json
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth

load_dotenv()  # Load .env file

# =============================================================================
# STAFF PORTAL SECURITY
# =============================================================================
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Rate limiter — blocks brute force on staff login
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],          # no global limit — only applied per route
    storage_uri='memory://',    # in-memory storage (no Redis needed)
)

# Staff secret code — required on every owner/kitchen login
# Set STAFF_SECRET_CODE in your .env file
_STAFF_SECRET = os.environ.get('STAFF_SECRET_CODE', '')

# =============================================================================
# FIREBASE AUTH — the ONLY auth mechanism for the Flutter mobile app
#
# Flutter sends:  Authorization: Bearer <firebase_id_token>
# Backend calls:  verify_firebase_id_token(token) → decoded payload → user
#
# JWT (HS256) is kept ONLY for the browser staff portal (login_staff.html).
# The Flutter app never uses or stores HS256 JWTs.
#
# ── To fix properly (one-time, 2 minutes) ────────────────────────────────────
#   1. Firebase Console → Project Settings → Service Accounts
#   2. Click "Generate new private key" → download JSON
#   3. Save as ./firebase-credentials.json  (same folder as app.py)
#
# ── Dev shortcut (no service account file) ───────────────────────────────────
#   Add  FIREBASE_SKIP_VERIFY=true  to .env
#   This trusts token claims without signature verification. Dev only!
# =============================================================================

_firebase_creds_path = os.environ.get('FIREBASE_CREDENTIALS_PATH', './firebase-credentials.json')
_firebase_project_id = os.environ.get('FIREBASE_PROJECT_ID', '')
_skip_verify         = os.environ.get('FIREBASE_SKIP_VERIFY', 'false').lower() == 'true'
_firebase_admin_ok   = False

if os.path.exists(_firebase_creds_path):
    try:
        _cred = credentials.Certificate(_firebase_creds_path)
        firebase_admin.initialize_app(_cred)
        _firebase_admin_ok = True
        print(f"[FIREBASE] ✅ Admin SDK initialized from {_firebase_creds_path}")
    except Exception as e:
        print(f"[FIREBASE] ⚠️  {_firebase_creds_path} is invalid: {e}")
        print(f"[FIREBASE]    → Get the real file: Firebase Console → Project Settings → Service Accounts → Generate new private key")
        try:
            firebase_admin.initialize_app()
        except Exception:
            pass
else:
    print(f"[FIREBASE] ⚠️  {_firebase_creds_path} not found.")
    print(f"[FIREBASE]    → Get it: Firebase Console → Project Settings → Service Accounts → Generate new private key")
    try:
        firebase_admin.initialize_app()
    except Exception:
        pass

if _skip_verify:
    print(f"[FIREBASE] ⚠️  FIREBASE_SKIP_VERIFY=true — signature check DISABLED (dev only!)")

import base64 as _base64
import time as _time


def _decode_token_claims_only(id_token: str) -> dict:
    """Decode token payload WITHOUT verifying signature. Dev/fallback only."""
    parts = id_token.split('.')
    if len(parts) != 3:
        raise ValueError("Malformed token: expected 3 parts")
    padded = parts[1] + '=' * (4 - len(parts[1]) % 4)
    payload = json.loads(_base64.urlsafe_b64decode(padded))
    now = _time.time()
    if payload.get('exp', 0) < now:
        raise ValueError("Firebase token has expired")
    if payload.get('aud') != _firebase_project_id:
        raise ValueError(
            f"Token audience mismatch: got '{payload.get('aud')}', "
            f"expected '{_firebase_project_id}'. "
            f"Check FIREBASE_PROJECT_ID in .env"
        )
    if payload.get('iss') != f"https://securetoken.google.com/{_firebase_project_id}":
        raise ValueError(f"Token issuer mismatch: {payload.get('iss')}")
    if not payload.get('sub'):
        raise ValueError("Token missing 'sub' claim")
    payload['uid'] = payload['sub']
    return payload


def verify_firebase_id_token(id_token: str) -> dict:
    """
    Verify a Firebase ID Token and return the decoded payload.

    Priority:
      1. Admin SDK  (requires firebase-credentials.json)  — full signature check
      2. FIREBASE_SKIP_VERIFY=true                        — claims only, no signature (dev)
      3. Neither → raises with a clear actionable message

    Also fast-rejects HS256 tokens (internal staff JWT) immediately.
    """
    # Fast-reject legacy HS256 staff tokens — not Firebase tokens
    try:
        hdr_raw = id_token.split('.')[0] + '=='
        hdr = json.loads(_base64.urlsafe_b64decode(hdr_raw))
        if hdr.get('alg', '').upper() == 'HS256':
            raise ValueError("Not a Firebase token (HS256 internal JWT)")
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Unreadable token header: {e}")

    if _firebase_admin_ok:
        return firebase_auth.verify_id_token(id_token)

    if _skip_verify:
        payload = _decode_token_claims_only(id_token)
        print(f"[FIREBASE] ⚠️  Dev mode: claims accepted without signature (uid={payload.get('uid')})")
        return payload

    raise ValueError(
        "Cannot verify Firebase token: firebase-credentials.json not found and "
        "FIREBASE_SKIP_VERIFY is not enabled.\n"
        "  Option A (recommended): download service account JSON from Firebase Console\n"
        "  Option B (dev only):    add FIREBASE_SKIP_VERIFY=true to .env"
    )


app = Flask(__name__)

# ==================== CSP HEADERS ====================
@app.after_request
def add_security_headers(response):
    # Comprehensive CSP to allow all necessary external resources
    csp = (
        "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: "
        "https://*.google.com https://*.googleapis.com https://*.gstatic.com "
        "https://api.qrserver.com https://cdnjs.cloudflare.com https://actions.google.com;"
        "img-src 'self' data: blob: https://*.google.com https://api.qrserver.com;"
        "media-src 'self' https://actions.google.com;"
    )
    response.headers['Content-Security-Policy'] = csp
    return response

# FIXED: Complete CORS configuration for all environments
CORS(app, resources={
    r"/*": {
        "origins": "*",  # Allow all origins for development
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "expose_headers": ["Content-Type", "Authorization"],
        "supports_credentials": False
    }
})

# Configuration
# ── DATABASE URL (Supabase PostgreSQL) ────────────────────────────────────────
# Local dev:   postgresql://postgres:password@localhost:5432/canteen_db
#
# Supabase (production) — use the POOLER URL (port 6543) NOT the direct URL:
#   Project Settings → Database → Connection Pooling → Connection String
#   Looks like: postgresql://postgres:pass@db.xxxx.supabase.co:6543/postgres
#
# Why port 6543 (pooler) instead of 5432 (direct)?
#   - Supports many concurrent connections from Render's multiple workers
#   - Lower latency, better performance on free tier
#   - Supabase recommends pooler for all server-side apps
#
# Set DATABASE_URL in Render dashboard → Environment Variables
# ─────────────────────────────────────────────────────────────────────────────
_db_url = os.environ.get(
    'DATABASE_URL',
    'postgresql://postgres:password@localhost:5432/canteen_db'
)
# Supabase (and some older platforms) gives URLs starting with "postgres://"
# SQLAlchemy 2.x requires "postgresql://"
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mmcoe-secret-key-2025-super-secure')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
limiter.init_app(app)

# OTP storage (in-memory for demo - no email service required)
otp_storage = {}
demo_payments = {}



# ==================== HELPER FUNCTIONS ====================

def generate_token(user_id, remember_me=False, staff=False):
    # Staff tokens: 8 hours (forces daily re-login)
    # Customer tokens: 7 days (or 30 days with remember_me)
    if staff:
        expiry = datetime.utcnow() + timedelta(hours=8)
    else:
        days = 30 if remember_me else 7
        expiry = datetime.utcnow() + timedelta(days=days)
    payload = {
        'user_id': user_id,
        'exp': expiry
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')

def verify_token(token):
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload['user_id']
    except Exception as e:
        print(f"Token verification failed: {e}")
        return None

def get_auth_user():
    """
    Authenticate any API request.

    Flutter mobile app  → sends Firebase ID Token (RS256)
                          → verified via verify_firebase_id_token()
                          → looks up user by firebase_uid

    Browser staff portal → sends internal HS256 JWT (from /api/auth/login/staff)
                          → verified via verify_token()
                          → looks up user by id
    """
    try:
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return None

        token = auth_header[7:].strip()
        if not token:
            return None

        # ── Try 1: Firebase ID Token (Flutter mobile app) ────────────────────
        try:
            decoded = verify_firebase_id_token(token)
            uid = decoded.get('uid')
            if uid:
                user = User.query.filter_by(firebase_uid=uid).first()
                if user:
                    print(f"[AUTH] ✅ Firebase: {user.name} (uid: {uid[:8]}...)")
                    return user
                print(f"[AUTH] ⚠️  firebase_uid {uid[:8]}... not in DB — needs google-login first")
                return None
        except ValueError:
            pass  # HS256 token or claim mismatch — fall through to JWT check
        except Exception as e:
            print(f"[AUTH] Firebase check error: {e}")

        # ── Try 2: Internal HS256 JWT (browser staff/owner portal) ───────────
        user_id = verify_token(token)
        if not user_id:
            return None

        user = User.query.get(user_id)
        if not user:
            print(f"[AUTH] ⚠️  JWT user_id {user_id} not found in DB")
            return None

        print(f"[AUTH] ✅ JWT: {user.name} (ID: {user.id}, role: {user.role})")
        return user

    except Exception as e:
        print(f"[AUTH] ❌ Unexpected error: {e}")
        return None


def generate_otp():
    return ''.join(random.choices(string.digits, k=4))

# ==================== AUTH DECORATORS ====================
from functools import wraps

def login_required(f):
    """Decorator: require valid JWT (from cookie or header)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get('authToken')
        if not token:
            auth_header = request.headers.get('Authorization', '')
            token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else None
        if not token:
            return redirect('/login/customer')
        user_id = verify_token(token)
        if not user_id:
            return redirect('/login/customer')
        return f(*args, **kwargs)
    return decorated

def role_required(*allowed_roles):
    """Decorator: require user to have one of the allowed roles."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = request.cookies.get('authToken')
            if not token:
                auth_header = request.headers.get('Authorization', '')
                token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else None
            # Redirect to staff login if no token and route needs owner/kitchen
            staff_roles = {'owner', 'kitchen'}
            if not token:
                if staff_roles.intersection(set(allowed_roles)):
                    return redirect('/login/staff')
                return redirect('/login/customer')
            user_id = verify_token(token)
            if not user_id:
                if staff_roles.intersection(set(allowed_roles)):
                    return redirect('/login/staff')
                return redirect('/login/customer')
            user = User.query.get(user_id)
            if not user or user.role not in allowed_roles:
                if staff_roles.intersection(set(allowed_roles)):
                    return redirect('/login/staff')
                return redirect('/login/customer')
            return f(*args, **kwargs)
        return decorated
    return decorator

# ==================== ROUTES ====================

@app.route('/', methods=['GET'])
def home():
    # Serve landing/login UI on root
    return render_template('landing.html')

@app.route('/login/customer', methods=['GET'])
def login_customer():
    return render_template('download_app.html')

@app.route('/login/staff', methods=['GET'])
def login_staff():
    return render_template('login_staff.html')

@app.route('/api/auth/generate-otp', methods=['POST', 'OPTIONS'])
def api_generate_otp():
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        data = request.get_json()
        phone = data.get('phone', '').strip()
        email = data.get('email', '').strip().lower()
        name = data.get('name', 'User')
        
        if not phone:
            return jsonify({'error': 'Phone number is required'}), 400
        
        # Generate and store OTP
        otp = generate_otp()
        otp_storage[phone] = {
            'otp': otp,
            'timestamp': datetime.utcnow(),
            'name': name,
            'email': email
        }
        
        # Clean old OTPs (older than 10 minutes)
        current_time = datetime.utcnow()
        expired_phones = [
            p for p, data in otp_storage.items()
            if (current_time - data['timestamp']).total_seconds() > 600
        ]
        for p in expired_phones:
            del otp_storage[p]
        
        print(f"\n[OTP] GENERATED")
        print(f"   Phone: {phone}")
        print(f"   Email: {email}")
        print(f"   Name: {name}")
        print(f"   OTP: {otp}")
        print(f"   Time: {current_time.strftime('%H:%M:%S')}\n")
        
        return jsonify({
            'success': True,
            'message': f'OTP sent successfully (Console Logged)',
            'otp': otp,  # In production, remove this and send via SMS/Email
            'note': 'For demo: OTP is shown here.'
        }), 200
        
    except Exception as e:
        print(f"OTP Generation Error: {e}")
        return jsonify({'error': str(e)}), 500

# ==================== NEW MODELS (ADD-ONLY) ====================

# Additive fields to Order and User (nullable to preserve existing data)
if not hasattr(Order, 'kitchen_status'):
    Order.kitchen_status = db.Column(db.String(20), default='pending', nullable=True)
if not hasattr(Order, 'preparation_started_at'):
    Order.preparation_started_at = db.Column(db.DateTime, nullable=True)
if not hasattr(Order, 'preparation_completed_at'):
    Order.preparation_completed_at = db.Column(db.DateTime, nullable=True)
if not hasattr(Order, 'kitchen_notes'):
    Order.kitchen_notes = db.Column(db.String(500), nullable=True)

if not hasattr(User, 'is_vip'):
    User.is_vip = db.Column(db.Boolean, default=False, nullable=True)
if not hasattr(User, 'is_blocked'):
    User.is_blocked = db.Column(db.Boolean, default=False, nullable=True)
if not hasattr(User, 'referred_by'):
    User.referred_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

# === NEW FEATURE: ADMIN PORTAL ADVANCED ===
admin_advanced_bp = Blueprint('admin_advanced', __name__, template_folder='templates')

@app.route('/admin-advanced', methods=['GET'])
@role_required('owner')
def admin_advanced():
    return render_template('admin_advanced.html')

# Add to User model: is_vip, is_blocked fields ONLY IF NOT EXIST
if not hasattr(User, 'is_vip'):
    User.is_vip = db.Column(db.Boolean, default=False)
if not hasattr(User, 'is_blocked'):
    User.is_blocked = db.Column(db.Boolean, default=False)
# Add to Staff/Employee model as needed

@app.route('/api/auth/signup', methods=['POST', 'OPTIONS'])
def signup():
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        data = request.get_json()
        
        # Validation
        required = ['name', 'email', 'phone', 'password'] # College ID is now optional
        missing = [f for f in required if not data.get(f)]
        
        if missing:
            return jsonify({'error': f'Missing fields: {", ".join(missing)}'}), 400
        
        # Verify OTP
        phone = data.get('phone', '').strip()
        email = data.get('email', '').strip().lower()
        otp = data.get('otp', '').strip()
        
        if not otp:
            return jsonify({'error': 'OTP is required'}), 400
        
        # Check if OTP exists for this phone
        if phone not in otp_storage:
            return jsonify({'error': 'OTP not found. Please request a new OTP'}), 400
        
        stored_otp_data = otp_storage[phone]
        stored_otp = stored_otp_data['otp']
        
        # Check if OTP is expired (10 minutes)
        if (datetime.utcnow() - stored_otp_data['timestamp']).total_seconds() > 600:
            del otp_storage[phone]
            return jsonify({'error': 'OTP expired. Please request a new OTP'}), 400
        
        # Verify OTP matches
        if otp != str(stored_otp):
            return jsonify({'error': 'Invalid OTP'}), 400
        
        # OTP verified, remove it from storage
        del otp_storage[phone]
        
        # Check existing user
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'Email already registered'}), 400
        
        if data.get('college_id'):
            if User.query.filter_by(college_id=data['college_id']).first():
                return jsonify({'error': 'College ID already registered'}), 400
        
        # Determine role based on college_id
        role = 'customer'
        if data.get('college_id'):
            college_id_lower = data['college_id'].lower()
            if 'owner' in college_id_lower or 'admin' in college_id_lower:
                role = 'owner'
            elif 'kitchen' in college_id_lower or 'staff' in college_id_lower:
                role = 'kitchen'
        
        # Create user
        user = User(
            name=data['name'].strip(),
            email=email,  # Use normalized email from OTP verification
            phone=data['phone'].strip(),
            college_id=data.get('college_id', '').strip() if data.get('college_id') else None,
            password=generate_password_hash(data['password']),
            role=role,
            department=data.get('department', '').strip(),
            year=data.get('year', '').strip(),
            address=data.get('address', '').strip()
        )
        
        db.session.add(user)
        db.session.commit()
        
        token = generate_token(user.id)
        
        print(f"\n✅ NEW USER REGISTERED")
        print(f"   Name: {user.name}")
        print(f"   Email: {user.email}")
        print(f"   Role: {user.role}\n")
        
        resp = make_response(jsonify({
            'success': True,
            'message': 'Signup successful',
            'token': token,
            'user': {
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'role': user.role,
                'phone': user.phone,
                'college_id': user.college_id,
                'department': user.department,
                'year': user.year,
                'address': user.address
            }
        }), 201)
        resp.set_cookie('authToken', token, httponly=False, samesite='Lax', max_age=7*24*3600)
        return resp
   

        
    except Exception as e:
        db.session.rollback()
        print(f"Signup Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/login/customer', methods=['POST', 'OPTIONS'])
def login_customer_api():
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        data = request.get_json()
        
        # Customer Login: Phone + Password
        identifier = data.get('identifier') or data.get('phone') or data.get('email') # 'email' key fallback for legacy
        password = data.get('password')

        if not identifier or not password:
            return jsonify({'error': 'Phone number and password are required'}), 400
        
        identifier = identifier.strip()
        
        # Find user primarily by PHONE (or Email if legacy)
        user = User.query.filter(
            (User.phone == identifier) | 
            (User.email == identifier.lower()) 
        ).first()
        
        if not user:
            return jsonify({'error': 'Invalid credentials'}), 401
            
        # Enforce Customer Role
        if user.role != 'customer':
             return jsonify({'error': 'Access restricted to customers'}), 403

        if not check_password_hash(user.password, password):
            return jsonify({'error': 'Invalid credentials'}), 401
        
        token = generate_token(user.id)
        
        print(f"\n[LOGIN] CUSTOMER LOGIN: {user.phone}")
        
        resp = make_response(jsonify({
            'success': True,
            'message': 'Login successful',
            'token': token,
            'user': user.to_dict()
        }), 200)
        resp.set_cookie('authToken', token, httponly=False, samesite='Lax', max_age=7*24*3600)
        return resp
        
    except Exception as e:
        print(f"Login Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/login/otp', methods=['POST', 'OPTIONS'])
def login_otp_api():
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        data = request.get_json()
        phone = data.get('phone', '').strip()
        otp = data.get('otp', '').strip()
        
        if not phone or not otp:
            return jsonify({'error': 'Phone and OTP are required'}), 400
            
        # Verify OTP
        if phone not in otp_storage:
             return jsonify({'error': 'OTP not found or expired'}), 400
             
        stored = otp_storage[phone]
        if str(stored['otp']) != str(otp):
            return jsonify({'error': 'Invalid OTP'}), 400
            
        # OTP Valid - Clear it
        del otp_storage[phone]
        
        # Find User
        user = User.query.filter_by(phone=phone).first()
        if not user:
            return jsonify({'error': 'User not found. Please sign up first.'}), 404
            
        if user.role != 'customer':
             return jsonify({'error': 'Access restricted to customers'}), 403
             
        token = generate_token(user.id)
        print(f"\n[LOGIN] OTP LOGIN: {user.phone}")
        
        resp = make_response(jsonify({
            'success': True,
            'message': 'Login successful',
            'token': token,
            'user': {
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'phone': user.phone,
                'role': user.role,
                'college_id': user.college_id,
                'department': user.department,
                'year': user.year,
                'address': user.address,
                'wallet_balance': getattr(user, 'wallet_balance', 0.0)
            }
        }), 200)
        resp.set_cookie('authToken', token, httponly=False, samesite='Lax', max_age=7*24*3600)
        return resp
        
    except Exception as e:
        print(f"OTP Login Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/login/staff', methods=['POST', 'OPTIONS'])
@limiter.limit("5 per 15 minutes", error_message="Too many login attempts. Try again in 15 minutes.")
def login_staff_api():
    if request.method == 'OPTIONS':
        return '', 204

    try:
        data = request.get_json() or {}

        # ── Collect credentials ────────────────────────────────────────────
        identifier   = (data.get('identifier') or data.get('college_id') or '').strip()
        password     = (data.get('password') or '').strip()
        secret_code  = (data.get('secret_code') or '').strip()

        if not identifier or not password:
            return jsonify({'error': 'College ID and password are required'}), 400

        # ── Layer 1: Staff secret code check ──────────────────────────────
        if _STAFF_SECRET and secret_code != _STAFF_SECRET:
            print(f"[STAFF LOGIN] ❌ Wrong secret code from IP {get_remote_address()}")
            return jsonify({'error': 'Invalid credentials'}), 401

        # ── Layer 2: Find user by College ID ──────────────────────────────
        user = User.query.filter(
            (User.college_id == identifier) |
            (User.email == identifier.lower())
        ).first()

        if not user:
            return jsonify({'error': 'Invalid credentials'}), 401

        # ── Layer 3: Enforce owner/kitchen only ───────────────────────────
        if user.role not in ('owner', 'kitchen'):
            return jsonify({'error': 'Access restricted to staff'}), 403

        # ── Layer 4: Password check ───────────────────────────────────────
        if not check_password_hash(user.password, password):
            print(f"[STAFF LOGIN] ❌ Wrong password for {identifier} from IP {get_remote_address()}")
            return jsonify({'error': 'Invalid credentials'}), 401

        # ── All checks passed — issue 8-hour staff token ──────────────────
        token = generate_token(user.id, staff=True)

        print(f"\n[STAFF LOGIN] ✅ {user.name} ({user.role}) from IP {get_remote_address()}\n")

        resp = make_response(jsonify({
            'success': True,
            'message': 'Login successful',
            'token': token,
            'user': {
                'id': user.id,
                'name': user.name,
                'role': user.role,
                'college_id': user.college_id,
            }
        }), 200)
        # httponly=True — JS cannot read this cookie (XSS protection)
        # secure=True only on production HTTPS — auto-detect via env
        _is_production = os.environ.get('FLASK_ENV', 'development') == 'production'
        resp.set_cookie(
            'authToken', token,
            httponly=True,
            samesite='Lax',
            secure=_is_production,  # True on Render (HTTPS), False on local (HTTP)
            max_age=8 * 3600        # 8 hours — matches token expiry
        )
        return resp

    except Exception as e:
        print(f"[STAFF LOGIN] Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/google-sync', methods=['POST', 'OPTIONS'])
def google_sync():
    """Sync Google/Firebase user with backend DB and return JWT. (LEGACY - kept for backward compat)"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        data = request.get_json()
        email = (data.get('email') or '').strip().lower()
        name = (data.get('name') or 'Google User').strip()
        phone = (data.get('phone') or '').strip()
        firebase_uid = (data.get('firebase_uid') or '').strip()

        if not email:
            return jsonify({'error': 'Email is required'}), 400

        # Find existing user by email
        user = User.query.filter_by(email=email).first()

        if not user:
            # Auto-create user from Google Sign-In
            user = User(
                name=name,
                email=email,
                phone=phone or '0000000000',
                password=generate_password_hash(firebase_uid or 'google-user'),
                role='customer',
                firebase_uid=firebase_uid or None,
            )
            db.session.add(user)
            db.session.commit()
            print(f"\n✅ NEW GOOGLE USER CREATED: {user.email}\n")
        else:
            # Link firebase_uid if not already set
            if firebase_uid and not user.firebase_uid:
                user.firebase_uid = firebase_uid
                db.session.commit()
            print(f"\n[GOOGLE SYNC] Existing user found: {user.email} (ID: {user.id})\n")

        token = generate_token(user.id)

        resp = make_response(jsonify({
            'success': True,
            'token': token,
            'user': user.to_dict(),
        }), 200)
        resp.set_cookie('authToken', token, httponly=False, samesite='Lax', max_age=7*24*3600)
        return resp

    except Exception as e:
        db.session.rollback()
        print(f"Google Sync Error: {e}")
        return jsonify({'error': str(e)}), 500

# ==================== NEW FIREBASE AUTH ENDPOINTS ====================

@app.route('/api/auth/google-login', methods=['POST', 'OPTIONS'])
def google_login():
    """Verify Firebase ID Token and return user profile or signal new user."""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        data = request.get_json()
        id_token = (data.get('id_token') or '').strip()

        if not id_token:
            return jsonify({'error': 'id_token is required'}), 400

        # Verify Firebase ID Token server-side
        try:
            decoded_token = verify_firebase_id_token(id_token)
        except Exception as e:
            print(f"[GOOGLE-LOGIN] Token verification failed: {e}")
            return jsonify({'error': 'Invalid or expired Firebase token', 'code': 'TOKEN_INVALID'}), 401

        uid = decoded_token.get('uid', '')
        email = decoded_token.get('email', '')
        name = decoded_token.get('name', 'Google User')
        photo_url = decoded_token.get('picture', '')

        if not uid:
            return jsonify({'error': 'Could not extract UID from token'}), 401

        # Check if user exists by firebase_uid
        user = User.query.filter_by(firebase_uid=uid).first()

        if user:
            # Check if blocked
            if getattr(user, 'is_blocked', False):
                return jsonify({'error': 'Account suspended', 'code': 'ACCOUNT_BLOCKED'}), 403

            # Existing user — return profile + transaction summary
            total_used = db.session.query(func.coalesce(func.sum(Order.total_amount), 0)).filter(
                Order.user_id == user.id,
                Order.status.in_(['completed', 'delivered', 'pending'])
            ).scalar() or 0.0

            print(f"\n[GOOGLE-LOGIN] ✅ Existing user: {user.name} (firebase_uid: {uid})\n")

            return jsonify({
                'success': True,
                'user_exists': True,
                'profile': {
                    'name': user.name,
                    'college_id': user.college_id,
                    'department': user.department,
                    'year': user.year,
                    'email': user.email,
                    'role': user.role,
                    'wallet_balance': float(user.wallet_balance or 0.0),
                    'total_used': float(total_used),
                    'total_saved': 0.0,  # TODO: calculate when discount tracking is added
                }
            }), 200
        else:
            # Check if user exists by email (link existing account)
            existing_by_email = User.query.filter_by(email=email.lower()).first() if email else None
            if existing_by_email:
                existing_by_email.firebase_uid = uid
                db.session.commit()
                print(f"\n[GOOGLE-LOGIN] ✅ Linked firebase_uid to existing email user: {email}\n")
                
                total_used = db.session.query(func.coalesce(func.sum(Order.total_amount), 0)).filter(
                    Order.user_id == existing_by_email.id,
                    Order.status.in_(['completed', 'delivered', 'pending'])
                ).scalar() or 0.0

                return jsonify({
                    'success': True,
                    'user_exists': True,
                    'profile': {
                        'name': existing_by_email.name,
                        'college_id': existing_by_email.college_id,
                        'department': existing_by_email.department,
                        'year': existing_by_email.year,
                        'email': existing_by_email.email,
                        'role': existing_by_email.role,
                        'wallet_balance': float(existing_by_email.wallet_balance or 0.0),
                        'total_used': float(total_used),
                        'total_saved': 0.0,
                    }
                }), 200

            # Truly new user — signal frontend to show profile form
            print(f"\n[GOOGLE-LOGIN] 🆕 New user detected: {email} (firebase_uid: {uid})\n")
            return jsonify({
                'success': True,
                'new_user': True,
                'firebase_uid': uid,
                'email': email,
                'name': name,
                'photo_url': photo_url,
                'show_form': True,
            }), 200

    except Exception as e:
        db.session.rollback()
        print(f"Google Login Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/debug-token', methods=['POST', 'OPTIONS'])
def debug_token():
    """
    DEV ONLY — test Firebase token verification without the full login flow.
    POST { "id_token": "<Firebase ID token>" }
    Returns the decoded payload or the exact error message.
    Remove or protect this endpoint before going to production.
    """
    if request.method == 'OPTIONS':
        return '', 204
    data = request.get_json(silent=True) or {}
    token = (data.get('id_token') or '').strip()
    if not token:
        return jsonify({'error': 'id_token required'}), 400
    try:
        decoded = verify_firebase_id_token(token)
        return jsonify({'success': True, 'decoded': decoded}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/auth/complete-profile', methods=['POST', 'OPTIONS'])
def complete_profile():
    """Create a new user after Google Sign-In profile completion."""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        data = request.get_json()
        id_token = (data.get('id_token') or '').strip()
        firebase_uid_from_body = (data.get('firebase_uid') or '').strip()
        name = (data.get('name') or '').strip()
        college_id = (data.get('college_id') or '').strip() or None
        department = (data.get('department') or '').strip() or None
        year = (data.get('year') or '').strip() or None

        if not name:
            return jsonify({'error': 'Name is required'}), 400
        if not id_token:
            return jsonify({'error': 'id_token is required for verification'}), 400

        # Re-verify token
        try:
            decoded_token = verify_firebase_id_token(id_token)
        except Exception as e:
            print(f"[COMPLETE-PROFILE] Token verification failed: {e}")
            return jsonify({'error': 'Invalid or expired Firebase token', 'code': 'TOKEN_INVALID'}), 401

        uid = decoded_token.get('uid', '')
        email = decoded_token.get('email', '')

        # Ensure firebase_uid matches token
        if firebase_uid_from_body and firebase_uid_from_body != uid:
            return jsonify({'error': 'Firebase UID mismatch', 'code': 'UID_MISMATCH'}), 400

        # Check if user already exists
        if User.query.filter_by(firebase_uid=uid).first():
            return jsonify({'error': 'User with this Firebase UID already exists', 'code': 'USER_EXISTS'}), 409

        # Check duplicate college_id
        if college_id:
            if User.query.filter_by(college_id=college_id).first():
                return jsonify({'error': 'College ID already registered to another account', 'code': 'DUPLICATE_COLLEGE_ID'}), 409

        # Validate year
        if year and year.upper() not in ('FE', 'SE', 'TE', 'BE'):
            return jsonify({'error': 'Year must be one of: FE, SE, TE, BE'}), 400

        # Create user
        user = User(
            firebase_uid=uid,
            name=name,
            email=email.lower() if email else f'{uid}@firebase.user',
            phone='0000000000',  # placeholder — not collected in Google flow
            password=generate_password_hash(uuid.uuid4().hex),  # random hash, never used
            role='customer',
            college_id=college_id,
            department=department,
            year=year.upper() if year else None,
        )
        db.session.add(user)
        db.session.commit()

        print(f"\n✅ NEW FIREBASE USER CREATED: {user.name} ({user.email}, uid: {uid})\n")

        return jsonify({
            'success': True,
            'message': 'Profile created successfully',
            'profile': {
                'name': user.name,
                'college_id': user.college_id,
                'department': user.department,
                'year': user.year,
                'email': user.email,
                'total_used': 0.0,
                'total_saved': 0.0,
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        print(f"Complete Profile Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/profile/<firebase_uid>', methods=['GET', 'OPTIONS'])
def get_profile_by_uid(firebase_uid):
    """Fetch user profile + transaction summary by firebase_uid."""
    if request.method == 'OPTIONS':
        return '', 204

    user = get_auth_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        # Allow users to view own profile, or staff/owner to view any
        target_user = User.query.filter_by(firebase_uid=firebase_uid).first()
        if not target_user:
            return jsonify({'error': 'User not found'}), 404

        if user.firebase_uid != firebase_uid and user.role not in ('owner', 'kitchen', 'admin'):
            return jsonify({'error': 'Access denied'}), 403

        # Transaction summary
        total_used = db.session.query(func.coalesce(func.sum(Order.total_amount), 0)).filter(
            Order.user_id == target_user.id,
            Order.status.in_(['completed', 'delivered', 'pending'])
        ).scalar() or 0.0

        total_orders = db.session.query(func.count(Order.id)).filter(
            Order.user_id == target_user.id
        ).scalar() or 0

        last_order = db.session.query(func.max(Order.created_at)).filter(
            Order.user_id == target_user.id
        ).scalar()

        return jsonify({
            'success': True,
            'profile': {
                'name': target_user.name,
                'college_id': target_user.college_id,
                'department': target_user.department,
                'year': target_user.year,
                'email': target_user.email,
                'wallet_balance': float(target_user.wallet_balance or 0.0),
            },
            'summary': {
                'total_used': float(total_used),
                'total_saved': 0.0,
                'total_orders': total_orders,
                'last_order_date': last_order.isoformat() if last_order else None,
            }
        }), 200

    except Exception as e:
        print(f"Profile by UID Error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/profile/summary/<firebase_uid>', methods=['GET', 'OPTIONS'])
def get_profile_summary(firebase_uid):
    """Lightweight transaction summary by firebase_uid."""
    if request.method == 'OPTIONS':
        return '', 204

    user = get_auth_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        target_user = User.query.filter_by(firebase_uid=firebase_uid).first()
        if not target_user:
            return jsonify({'error': 'User not found'}), 404

        total_used = db.session.query(func.coalesce(func.sum(Order.total_amount), 0)).filter(
            Order.user_id == target_user.id,
            Order.status.in_(['completed', 'delivered', 'pending'])
        ).scalar() or 0.0

        total_orders = db.session.query(func.count(Order.id)).filter(
            Order.user_id == target_user.id
        ).scalar() or 0

        return jsonify({
            'total_used': float(total_used),
            'total_saved': 0.0,
            'total_orders': total_orders,
            'wallet_balance': float(target_user.wallet_balance or 0.0),
        }), 200

    except Exception as e:
        print(f"Profile Summary Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/profile', methods=['GET', 'OPTIONS'])
def get_profile():
    if request.method == 'OPTIONS':
        return '', 204
    
    user = get_auth_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        # Get wallet balance (handle if column doesn't exist)
        wallet = float(getattr(user, 'wallet_balance', 0.0) or 0.0)
        is_vip = bool(getattr(user, 'is_vip', False))
        
        return jsonify({
            'success': True,
            'user': {
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'phone': user.phone,
                'role': user.role,
                'college_id': user.college_id,
                'department': user.department,
                'year': user.year,
                'address': user.address,
                'wallet_balance': wallet,
                'is_vip': is_vip
            }
        }), 200
    except Exception as e:
        print(f"Profile Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/menu/all', methods=['GET', 'OPTIONS'])
def get_all_menu():
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        items = MenuItem.query.all()
        return jsonify([{
            'id': item.id,
            'name': item.name,
            'icon': item.icon,
            'price': item.price,
            'desc': item.description,
            'category': item.category,
            'available': item.available,
            'tags': item.tags,
            'image_url': item.image_url or ''
        } for item in items]), 200
    except Exception as e:
        print(f"Menu Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/menu/today', methods=['GET', 'OPTIONS'])
def get_today_menu():
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        items = MenuItem.query.filter_by(available=True).all()
        
        # Check for active offer
        active_offer = Offer.query.filter(
            Offer.is_active == True,
            Offer.start_date <= datetime.utcnow(),
            or_(Offer.end_date.is_(None), Offer.end_date >= datetime.utcnow())
        ).order_by(Offer.created_at.desc()).first()
        
        discount_percent = 0
        if active_offer:
            discount_percent = active_offer.discount_percent
        
        result = []
        for item in items:
            original_price = item.price
            discounted_price = original_price
            if discount_percent > 0:
                discounted_price = original_price * (1 - discount_percent / 100)
            
            result.append({
                'id': item.id,
                'name': item.name,
                'icon': item.icon,
                'price': round(discounted_price, 2),
                'original_price': original_price,
                'discount_percent': discount_percent,
                'desc': item.description,
                'category': item.category,
                'tags': item.tags,
                'image_url': item.image_url or ''
            })
        
        return jsonify(result), 200
    except Exception as e:
        print(f"Today Menu Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/orders/create', methods=['POST', 'OPTIONS'])
def create_order():
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        user = get_auth_user()
        if not user:
            return jsonify({'error': 'Unauthorized - Please login'}), 401
        
        data = request.get_json() or {}
        if not data or (not data.get('items') and not data.get('combos')):
            return jsonify({'error': 'Items or combos are required'}), 400
        
        # Generate unique order ID using timestamp + random suffix
        import random
        order_id = f"ORD{int(datetime.utcnow().timestamp())}{random.randint(100,999)}"
        # Ensure uniqueness
        while Order.query.filter_by(order_id=order_id).first():
            order_id = f"ORD{int(datetime.utcnow().timestamp())}{random.randint(100,999)}"
        
        # Calculate total from items and combos (respect active offer discounts and combos added as items)
        calculated_total = 0.0
        # Determine active offer discount percent (replicates logic from get_today_menu)
        discount_percent = 0
        try:
            active_offer = Offer.query.filter(
                Offer.is_active == True,
                Offer.start_date <= datetime.utcnow(),
                or_(Offer.end_date.is_(None), Offer.end_date >= datetime.utcnow())
            ).order_by(Offer.created_at.desc()).first()
            if active_offer:
                discount_percent = active_offer.discount_percent or 0
        except Exception:
            discount_percent = 0

        # Track combos inferred from items with ids like 'combo_<id>'
        inferred_combos = []

        # Add items total (apply offer discount); detect combos passed as items
        for item in data.get('items', []):
            item_id = item.get('id')
            qty = int(item.get('quantity', 1))
            # Detect combo items sent as 'combo_<id>' to avoid total becoming 0
            if isinstance(item_id, str) and item_id.startswith('combo_'):
                try:
                    combo_id = int(item_id.split('_', 1)[1])
                    combo = Combo.query.get(combo_id)
                    if combo and combo.available:
                        calculated_total += float(combo.price) * qty
                        inferred_combos.append({'id': combo_id, 'quantity': qty})
                except Exception:
                    pass
                continue
            # Regular menu item path
            menu_item = MenuItem.query.get(item_id)
            if menu_item:
                unit_price = float(menu_item.price)
                if discount_percent and discount_percent > 0:
                    unit_price = unit_price * (1 - float(discount_percent) / 100.0)
                calculated_total += unit_price * qty

        # Add combos total explicitly provided
        for combo_data in data.get('combos', []):
            combo = Combo.query.get(combo_data.get('id'))
            if combo and combo.available:
                calculated_total += float(combo.price) * int(combo_data.get('quantity', 1))
        
        # Use provided total if it matches calculated (allows for discounts), otherwise use calculated
        provided_total = float(data.get('total', 0))
        if provided_total > 0 and abs(provided_total - calculated_total) < 0.01:
            calculated_total = provided_total
        
        # Handle wallet payment
        payment_method = data.get('payment_method', 'online')
        transaction_id = data.get('transaction_id', 'DEMO-TXN')
        
        if payment_method == 'wallet':
            transaction_id = 'WALLET' # Wallet has special handling below
        
        # IDEMPOTENCY CHECK: If transaction_id exists (and is not DEMO-TXN or WALLET which recur), return existing order
        if transaction_id and transaction_id not in ['DEMO-TXN', 'WALLET']:
            existing_order = Order.query.filter_by(transaction_id=transaction_id).first()
            if existing_order:
                print(f"\n⚠️ DUPLICATE TRANSACTION DETECTED: {transaction_id}")
                print(f"   Returning existing order: {existing_order.order_id}\n")
                
                # Fetch coupon for this order to return full details
                existing_coupon = Coupon.query.filter_by(order_id=existing_order.id).first()
                coupon_id = existing_coupon.coupon_id if existing_coupon else 'UNKNOWN'
                qr_data = existing_coupon.qr_data if existing_coupon else '{}'
                
                return jsonify({
                    'success': True,
                    'message': 'Order already received',
                    'order_id': existing_order.order_id,
                    'coupon_id': coupon_id,
                    'qr_data': qr_data,
                    'existing': True
                }), 200

        if payment_method == 'wallet':
            # Fetch fresh user data to get wallet balance
            user = User.query.get(user.id)
            wallet_balance = float(getattr(user, 'wallet_balance', 0.0) or 0.0)
            
            if wallet_balance < calculated_total:
                return jsonify({'error': f'Insufficient wallet balance. Available: ₹{wallet_balance}, Required: ₹{calculated_total}'}), 400
            
            # Deduct from wallet
            user.wallet_balance = wallet_balance - calculated_total
            transaction_id = 'WALLET'
            print(f"Payment via wallet: ₹{calculated_total} deducted. Remaining balance: ₹{user.wallet_balance}")
        
        order = Order(
            order_id=order_id,
            user_id=user.id,
            customer_name=user.name,
            customer_phone=user.phone,
            total_amount=calculated_total,
            transaction_id=transaction_id,
            status='pending'
        )
        
        db.session.add(order)
        db.session.flush()
        
        # Add order items (support both regular items and combos)
        order_items_data = []
        
        # Handle regular menu items (apply the same discount to captured unit price)
        for item in data.get('items', []):
            item_id = item.get('id')
            qty = int(item.get('quantity', 1))
            # Skip combos that were passed as items - handled below
            if isinstance(item_id, str) and item_id.startswith('combo_'):
                continue
            menu_item = MenuItem.query.get(item_id)
            if menu_item:
                unit_price = float(menu_item.price)
                if discount_percent and discount_percent > 0:
                    unit_price = unit_price * (1 - float(discount_percent) / 100.0)
                order_item = OrderItem(
                    order_id=order.id,
                    menu_item_id=menu_item.id,
                    quantity=qty,
                    price=unit_price
                )
                db.session.add(order_item)
                order_items_data.append({
                    'id': menu_item.id,
                    'name': menu_item.name,
                    'icon': menu_item.icon,
                    'quantity': qty,
                    'price': unit_price
                })
        
        # Handle combo items (from explicit combos + inferred combos from items)
        effective_combos = list(data.get('combos', [])) + inferred_combos
        for combo_data in effective_combos:
            combo = Combo.query.get(combo_data.get('id'))
            if combo and combo.available:
                # Add combo items to order
                for combo_item in combo.items:
                    menu_item = combo_item.menu_item
                    if menu_item:
                        order_item = OrderItem(
                            order_id=order.id,
                            menu_item_id=menu_item.id,
                            quantity=combo_item.quantity * int(combo_data.get('quantity', 1)),
                            price=menu_item.price
                        )
                        db.session.add(order_item)
                        order_items_data.append({
                            'id': menu_item.id,
                            'name': menu_item.name,
                            'icon': menu_item.icon,
                            'quantity': combo_item.quantity * int(combo_data.get('quantity', 1)),
                            'price': menu_item.price
                        })
        
        # Create coupon
        coupon_id = f"COUP{int(datetime.utcnow().timestamp())}"
        qr_data = f'{{"orderId":"{order_id}","amount":{calculated_total},"status":"pending","time":"{datetime.utcnow().isoformat()}"}}'
        
        coupon = Coupon(
            coupon_id=coupon_id,
            order_id=order.id,
            qr_data=qr_data,
            status='pending'
        )
        db.session.add(coupon)
        
        # Log to DailyOrderLog
        try:
            order_date = datetime.utcnow().date()
            order_time = datetime.utcnow()
            # Determine payment method
            if transaction_id == 'WALLET':
                payment_method = 'wallet'
            elif transaction_id == 'CASH':
                payment_method = 'cash'
            else:
                payment_method = 'online'
            
            daily_log = DailyOrderLog(
                order_id=order_id,
                order_db_id=order.id,
                user_id=user.id,
                customer_name=user.name,
                customer_phone=user.phone,
                customer_email=user.email,
                order_date=order_date,
                order_time=order_time,
                total_amount=order.total_amount,
                transaction_id=data.get('transaction_id', ''),
                payment_method=payment_method,
                status='pending',
                items_json=json.dumps(order_items_data)
            )
            db.session.add(daily_log)
        except Exception as e:
            print(f"Error creating daily log: {e}")
        
        db.session.commit()

        # Export CSV snapshots
        export_csv()
        
        print(f"\n✅ ORDER CREATED")
        print(f"   Order ID: {order_id}")
        print(f"   Customer: {user.name}")
        print(f"   Amount: ₹{data.get('total')}\n")
        
        return jsonify({
            'success': True,
            'order_id': order_id,
            'coupon_id': coupon_id,
            'qr_data': qr_data
        }), 201
        
    except Exception as e:
        db.session.rollback()
        print(f"Order Creation Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/orders/analytics', methods=['GET', 'OPTIONS'])
def get_order_analytics():
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        selected_date = request.args.get('date', date.today().isoformat())
        target_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        
        top_items = db.session.query(
            MenuItem.name,
            MenuItem.icon,
            func.sum(OrderItem.quantity).label('total_quantity'),
            func.sum(OrderItem.quantity * OrderItem.price).label('total_revenue')
        ).join(OrderItem).join(Order).filter(
            func.date(Order.created_at) == target_date
        ).group_by(MenuItem.id).order_by(desc('total_quantity')).limit(10).all()
        
        return jsonify([{
            'name': item.name,
            'icon': item.icon,
            'quantity': int(item.total_quantity),
            'revenue': float(item.total_revenue)
        } for item in top_items]), 200
        
    except Exception as e:
        print(f"Analytics Error: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== DEMO PAYMENT PAGES ====================

@app.route('/demo/create-payment', methods=['POST'])
def demo_create_payment():
    """Create a payment session"""
    try:
        data = request.get_json() or {}
        amount = float(data.get('amount', 0))
        note = str(data.get('note', 'MMCOE Order'))
        
        if amount <= 0:
            return jsonify({'error': 'Invalid amount'}), 400
        
        # Generate unique token using UUID
        token = str(uuid.uuid4())
        
        # Store payment session
        demo_payments[token] = {
            'token': token,
            'amount': amount,
            'note': note,
            'status': 'pending',  # IMPORTANT: Initial status
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
            'paid_at': None,
            'transaction_ref': f"TXN-{random.randint(100000,999999)}"
        }
        
        # Use relative URLs to avoid domain mismatch issues (ngrok vs localhost)
        base = request.host_url.rstrip('/')
        # For QR code, we need absolute URL, but for link clicking, relative works better
        pay_url_absolute = f"{base}/demo/pay/{token}"
        pay_url_relative = f"/demo/pay/{token}"
        status_url = f"/demo/pay/{token}/status"
        
        print(f"[PAYMENT] Created: {token} - Amount: {amount} - Status: pending")
        print(f"[PAYMENT] Pay URL (absolute): {pay_url_absolute}")
        print(f"[PAYMENT] Pay URL (relative): {pay_url_relative}")
        print(f"[PAYMENT] Status URL: {status_url}")
        print(f"[PAYMENT] Stored in demo_payments dict (total: {len(demo_payments)})")
        
        return jsonify({
            'success': True,
            'token': token,
            'amount': amount,
            'pay_url': pay_url_absolute,  # Absolute for QR code
            'pay_url_relative': pay_url_relative,  # Relative for direct links
            'status_url': status_url
        }), 201
    except Exception as e:
        print(f"[PAYMENT] Error creating payment: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/demo/pay/<token>', methods=['GET'])
def demo_pay_page(token):
    """Payment page where user clicks 'Pay Now'"""
    # Debug: Log token lookup attempt
    print(f"[PAYMENT PAGE] Looking up token: {token}")
    print(f"[PAYMENT PAGE] Available tokens: {list(demo_payments.keys())[:5]}")  # Show first 5 tokens
    print(f"[PAYMENT PAGE] Total payments in storage: {len(demo_payments)}")
    
    # Try to find the token (handle URL encoding)
    info = demo_payments.get(token)
    
    # If not found, try URL-decoded version
    if not info:
        try:
            from urllib.parse import unquote
            decoded_token = unquote(token)
            if decoded_token != token:
                print(f"[PAYMENT PAGE] Trying decoded token: {decoded_token}")
                info = demo_payments.get(decoded_token)
                if info:
                    token = decoded_token  # Use decoded token for rest of function
        except:
            pass
    
    if not info:
        print(f"[PAYMENT PAGE] ❌ Token not found: {token}")
        # Show available tokens for debugging (first 100 chars)
        debug_info = f"<p>Token searched: <code>{token}</code></p><p>Available tokens: {len(demo_payments)}</p>"
        return (f"""
<!DOCTYPE html><html><head><meta charset='utf-8'><title>Payment</title>
<style>body{{font-family:Segoe UI,Tahoma,Arial;margin:40px;color:#2C3E50}}
code{{background:#f0f0f0;padding:2px 6px;border-radius:4px;font-family:monospace}}</style></head><body>
<h2>Invalid Payment Link</h2>
<p>This payment session does not exist or has expired.</p>
{debug_info}
<p><a href="/app">← Back to App</a></p>
</body></html>
        """), 404
    
    paid = info['status'] == 'paid'
    amount = info['amount']
    note = info['note']
    
    return f'''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Payment Page - MMCOE</title>
<style>
        body {{
            font-family: 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
        }}
        .payment-card {{
            background: white;
            padding: 40px;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
            max-width: 400px;
            width: 90%;
        }}
        h1 {{ color: #2C3E50; margin-bottom: 20px; }}
        .amount {{
            font-size: 3em;
            color: #FF6B6B;
            font-weight: 800;
            margin: 20px 0;
        }}
        .btn {{
            background: linear-gradient(135deg, #FF6B6B 0%, #4ECDC4 100%);
            color: white;
            padding: 16px 40px;
            border: none;
            border-radius: 12px;
            font-size: 1.2em;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.3s;
            margin: 10px;
            width: 100%;
        }}
        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(255, 107, 107, 0.4);
        }}
        .btn:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}
        .btn-cancel {{
            background: #6B7280;
            margin-top: 10px;
        }}
        .status {{
            margin-top: 20px;
            padding: 15px;
            border-radius: 10px;
            font-weight: 600;
        }}
        .status.success {{
            background: #D1FAE5;
            color: #065F46;
        }}
        .status.error {{
            background: #FEE2E2;
            color: #991B1B;
        }}
        .info {{
            color: #6B7280;
            margin: 15px 0;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="payment-card">
        <h1>💳 Payment Demo</h1>
        <div class="amount">₹{amount}</div>
        <div class="info">{note}</div>
        
        <button id="payBtn" class="btn" onclick="processPayment()" {'disabled' if paid else ''}>
            {'✓ Paid' if paid else 'Pay Now'}
        </button>
        
        <button class="btn btn-cancel" onclick="window.close()">
            Cancel
        </button>
        
        <div id="status" class="status" style="display:none;"></div>
        
        <div class="info" style="margin-top: 20px;">
            This is a demo payment page.<br>
            Click "Pay Now" to simulate successful payment.
  </div>
    </div>
    
<script>
        const token = '{token}';
        const statusDiv = document.getElementById('status');
        const payBtn = document.getElementById('payBtn');
        
        async function processPayment() {{
            payBtn.disabled = true;
            payBtn.textContent = 'Processing...';
            
            try {{
                const response = await fetch('/demo/pay/' + token + '/confirm', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }}
                }});
                
                const result = await response.json();
                
                if (result.success) {{
                    statusDiv.className = 'status success';
                    statusDiv.innerHTML = '✅ Payment Successful!';
                    statusDiv.style.display = 'block';
                    payBtn.textContent = '✓ Paid';
                    
                    // Notify parent window
                    if (window.opener) {{
                        console.log('[PAYMENT PAGE] Notifying parent window');
    window.opener.postMessage({{
      type: 'payment_completed',
      token: token
    }}, '*');
  }}
  
                    // Auto-close after 2 seconds
                    setTimeout(function() {{
                        window.close();
                    }}, 2000);
                }} else {{
                    throw new Error(result.error || 'Payment failed');
                }}
            }} catch (error) {{
                statusDiv.className = 'status error';
                statusDiv.innerHTML = '❌ ' + error.message;
                statusDiv.style.display = 'block';
                payBtn.disabled = false;
                payBtn.textContent = 'Try Again';
            }}
        }}
        
        // Check if already paid on page load
    fetch('/demo/pay/' + token + '/status')
            .then(r => r.json())
            .then(data => {{
                if (data.status === 'paid') {{
                    statusDiv.className = 'status success';
                    statusDiv.innerHTML = '✅ Already Paid';
                    statusDiv.style.display = 'block';
                    payBtn.disabled = true;
                    payBtn.textContent = '✓ Paid';
                    
                    // Notify parent window if already paid
                    if (window.opener) {{
            window.opener.postMessage({{
              type: 'payment_completed',
              token: token
            }}, '*');
          }}
        }}
      }})
            .catch(e => console.error('Status check error:', e));
        
        // Periodic status check for payment done via QR scanner
        var statusCheckInterval = null;
        function checkStatus() {{
            fetch('/demo/pay/' + token + '/status')
                .then(r => r.json())
                .then(data => {{
                    if (data.status === 'paid') {{
                        statusDiv.className = 'status success';
                        statusDiv.innerHTML = '✅ Payment Successful!';
                        statusDiv.style.display = 'block';
                        payBtn.disabled = true;
                        payBtn.textContent = '✓ Paid';
                        
                        // Clear interval once paid
                        if (statusCheckInterval) {{
                            clearInterval(statusCheckInterval);
                            statusCheckInterval = null;
                        }}
                        
                        // Notify parent window
                        if (window.opener) {{
                            window.opener.postMessage({{
                                type: 'payment_completed',
                                token: token
                            }}, '*');
                        }}
                    }}
                }})
                .catch(e => console.error('Status check error:', e));
        }}
        
        // Check status every 2 seconds if not already paid
        {'' if paid else 'statusCheckInterval = setInterval(checkStatus, 2000);'}
        window.addEventListener('focus', function() {{
            if (!payBtn.disabled) {{
                checkStatus();
            }}
        }});
</script>
</body>
</html>
    '''

@app.route('/demo/pay/<token>/confirm', methods=['POST'])
def demo_pay_confirm(token):
    """Confirm payment (user clicked 'Pay Now')"""
    info = demo_payments.get(token)
    if not info:
        return jsonify({'error': 'Invalid token'}), 404
    
    # Update payment status
    info['status'] = 'paid'
    info['paid_at'] = datetime.utcnow().isoformat()
    info['updated_at'] = datetime.utcnow().isoformat()
    
    print(f"[PAYMENT] Confirmed: {token} - Status: PAID")
    
    return jsonify({
        'success': True,
        'status': 'paid',
        'token': token
    })

@app.route('/demo/pay/<token>/status', methods=['GET', 'OPTIONS'])
def demo_pay_status(token):
    """Check payment status - THIS IS THE KEY ENDPOINT FOR CROSS-DEVICE PAYMENT DETECTION"""
    if request.method == 'OPTIONS':
        return '', 204
    
    print(f"[PAYMENT STATUS] Checking token: {token}")
    
    info = demo_payments.get(token)
    if not info:
        print(f"[PAYMENT STATUS] Token not found: {token}")
        return jsonify({'error': 'Invalid token'}), 404
    
    status = info.get('status', 'pending')
    
    print(f"[PAYMENT STATUS] Token: {token} - Status: {status}")
    
    # CRITICAL: Return exact format expected by frontend
    response = jsonify({
        'status': status,  # 'pending' or 'paid'
        'token': token,
        'amount': info.get('amount', 0),
        'created_at': info.get('created_at'),
        'updated_at': info.get('updated_at'),
        'paid_at': info.get('paid_at')  # Include paid timestamp if available
    })
    
    # IMPORTANT: Add no-cache headers to ensure real-time status
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    return response

# Serve the SPA front-end directly from this Flask app to keep links consistent
@app.route('/app', methods=['GET'])
def serve_landing_html():
    try:
        return render_template('landing.html')
    except Exception as e:
        return f"Front-end not found: {e}", 404

# ==================== AUTH PAGES (SEPARATE) ====================
@app.route('/login/customer', methods=['GET'])
def login_customer_page():
    return render_template('auth/customer_login.html')

@app.route('/register/customer', methods=['GET'])
def register_customer_page():
    return render_template('auth/customer_register.html')

@app.route('/login/kitchen', methods=['GET'])
def login_kitchen_page():
    return render_template('auth/kitchen_login.html')

@app.route('/register/kitchen', methods=['GET'])
def register_kitchen_page():
    return render_template('auth/kitchen_register.html')

@app.route('/logout', methods=['GET'])
def logout_page():
    resp = make_response(redirect('/'))
    resp.delete_cookie('authToken')
    return resp

# ==================== HEALTH ENDPOINTS ====================
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'ok': True, 'time': datetime.utcnow().isoformat()}), 200

@app.route('/health/routes', methods=['GET'])
def health_routes():
    routes = [
        {'rule': str(r.rule), 'methods': list(r.methods), 'endpoint': r.endpoint}
        for r in app.url_map.iter_rules()
        if not r.rule.startswith('/static')
    ]
    return jsonify(routes), 200

# ==================== MULTI-PAGE ROUTES (NAV ITEMS) ====================
# Customer pages
@app.route('/dashboard/customer')
@app.route('/customer/dashboard')
@role_required('owner')
def customer_dashboard():
    return render_template('customer/browse_menu.html')

@app.route('/customer/browse-menu')
@role_required('owner')
def page_customer_browse_menu():
    return render_template('customer/browse_menu.html')

@app.route('/customer/cart')
@role_required('owner')
def page_customer_cart():
    return render_template('customer/cart.html')

@app.route('/customer/orders')
@role_required('owner')
def page_customer_orders():
    return render_template('customer/orders.html')

@app.route('/customer/coupons')
@role_required('owner')
def page_customer_coupons():
    return render_template('customer/coupons.html')

@app.route('/customer/history')
@role_required('owner')
def page_customer_history():
    return render_template('customer/history.html')

@app.route('/customer/profile')
@role_required('customer')
def page_customer_profile():
    return render_template('customer/profile.html')

@app.route('/customer/feedback')
@role_required('customer')
def page_customer_feedback():
    return render_template('customer/feedback.html')

@app.route('/customer/advanced-features')
@role_required('customer')
def page_customer_advanced_features():
    return render_template('customer/advanced_features.html')

# Owner pages
@app.route('/owner/dashboard')
@role_required('owner')
def page_owner_dashboard():
    return render_template('owner/dashboard.html')

@app.route('/owner/powerbi')
@role_required('owner')
def page_owner_powerbi():
    return render_template('owner/powerbi.html')

@app.route('/owner/top-dishes')
@role_required('owner')
def page_owner_top_dishes():
    return render_template('owner/top_dishes.html')

@app.route('/owner/pending-orders')
@role_required('owner')
def page_owner_pending_orders():
    return render_template('owner/pending_orders.html')

@app.route('/owner/todays-menu')
@role_required('owner')
def page_owner_todays_menu():
    return render_template('owner/todays_menu.html')

@app.route('/owner/kitchen')
@role_required('owner')
def page_owner_kitchen():
    return render_template('owner/kitchen.html')

@app.route('/owner/feedback')
@role_required('owner')
def page_owner_feedback():
    return render_template('owner/feedback.html')

@app.route('/owner/cash-order')
@role_required('owner')
def page_owner_cash_order():
    return render_template('owner/cash_order.html')

@app.route('/owner/customer-segments')
@role_required('owner')
def page_owner_customer_segments():
    return render_template('owner/customer_segments.html')

@app.route('/owner/history')
@role_required('owner')
def page_owner_history():
    return render_template('owner/history.html')

@app.route('/owner/offers')
@role_required('owner')
def page_owner_offers():
    return render_template('owner/offers.html')

@app.route('/owner/combos')
@role_required('owner')
def page_owner_combos():
    return render_template('owner/combos.html')

@app.route('/owner/daily-orders')
@role_required('owner')
def page_owner_daily_orders():
    return render_template('owner/daily_orders.html')

# Kitchen pages
@app.route('/kitchen/dashboard')
@role_required('kitchen', 'owner')
def page_kitchen_dashboard():
    return render_template('kitchen/dashboard.html')

@app.route('/kitchen/orders')
@role_required('kitchen', 'owner')
def page_kitchen_orders():
    return render_template('kitchen/orders.html')

@app.route('/kitchen/expire-coupons')
@role_required('kitchen', 'owner')
def page_kitchen_expire_coupons():
    return render_template('kitchen/expire_coupons.html')

@app.route('/kitchen/history')
@role_required('kitchen', 'owner')
def page_kitchen_history():
    return render_template('kitchen/history.html')

# ==================== ORDER SYNC ENDPOINTS ====================

def serialize_order(order: Order):
    try:
        # Safely check for VIP status
        vip = False
        if order.user_id:
            try:
                user_obj = User.query.get(order.user_id)
                if user_obj and hasattr(user_obj, 'is_vip'):
                    vip = bool(user_obj.is_vip)
            except Exception:
                pass
    except Exception:
        vip = False
    
    # Handle customer name - for cash orders, use customer_name field
    customer_name = order.customer_name or 'Walk-in Customer'
    if order.user_id:
        try:
            user_obj = User.query.get(order.user_id)
            if user_obj and user_obj.name:
                customer_name = user_obj.name
        except Exception:
            pass
    
    # Safely serialize items
    items_list = []
    try:
        for it in order.items:
            if it and it.menu_item:
                items_list.append({
                    'id': it.menu_item_id,
                    'name': it.menu_item.name or 'Unknown Item',
                    'icon': it.menu_item.icon or '🍽️',
                    'quantity': it.quantity,
                    'price': it.price,
                })
    except Exception as e:
        print(f"Error serializing order items for order {order.order_id}: {e}")
        items_list = []
    
    return {
        'id': order.order_id,
        'order_id': order.order_id,  # Added for frontend compatibility
        'db_id': order.id,
        'total': order.total_amount,
        'status': order.status,
        'timestamp': order.created_at.isoformat() if order.created_at else None,
        'created_at': order.created_at.isoformat() if order.created_at else None,  # Added for frontend
        'customer_name': customer_name,  # Added for frontend
        'transaction_id': order.transaction_id or '',  # Added for frontend
        'is_vip': vip,
        'kitchen_notes': order.kitchen_notes or '',
        'items': items_list
    }

@app.route('/api/orders/my-orders', methods=['GET', 'OPTIONS'])
def api_my_orders():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401
        orders = Order.query.filter_by(user_id=user.id).filter(Order.status != 'delivered').order_by(Order.created_at.desc()).all()
        return jsonify([serialize_order(o) for o in orders]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/orders/history', methods=['GET', 'OPTIONS'])
def api_order_history():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401
        orders = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).all()
        return jsonify([serialize_order(o) for o in orders]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== GET PENDING ORDERS (OWNER OR KITCHEN) ====================
@app.route('/api/orders/pending', methods=['GET', 'OPTIONS'])
def get_pending_orders():
    if request.method == 'OPTIONS':
        return '', 204
    user = get_auth_user()
    if not user or user.role not in ['owner','kitchen']:
        return jsonify({'error': 'Unauthorized'}), 401

    pending = Order.query.filter_by(status='pending').order_by(Order.created_at.desc()).all()
    result = []
    for order in pending:
        items = []
        for item in order.items:
            if item.menu_item:
                items.append({
                    'id': item.menu_item.id,
                    'name': item.menu_item.name,
                    'quantity': item.quantity,
                    'price': item.price,
                    'icon': item.menu_item.icon
                })
        # VIP flag for prioritization
        vip = False
        if order.user_id:
            try:
                user_obj = User.query.get(order.user_id)
                if user_obj and hasattr(user_obj, 'is_vip'):
                    vip = bool(user_obj.is_vip)
            except Exception:
                pass
        result.append({
            'id': order.id,
            'order_id': order.order_id,
            'customer_name': order.customer_name,
            'customer_phone': order.customer_phone,
            'items': items,
            'total': order.total_amount,
            'transaction_id': order.transaction_id,
            'created_at': order.created_at.isoformat() if order.created_at else None,
            'is_vip': vip
        })
    # Sort VIP first, then by created_at desc (already desc)
    result.sort(key=lambda x: (not x.get('is_vip', False), ), reverse=False)
    return jsonify(result), 200

# ==================== OWNER: ACCEPT ORDER FEATURE ====================
@app.route('/api/owner/orders/<int:order_id>/accept', methods=['PUT', 'OPTIONS'])
def owner_accept_order(order_id):
    """Owner accepts a pending order, changing its status to 'accepted' and allowing it to appear in kitchen queue."""
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        # Debug: Log incoming request headers
        auth_header = request.headers.get('Authorization', '')
        print(f"[ACCEPT ORDER] Authorization header: {auth_header[:50] if auth_header else 'NONE'}...")
        print(f"[ACCEPT ORDER] Request method: {request.method}")
        print(f"[ACCEPT ORDER] Request headers: {dict(request.headers)}")
        
        user = get_auth_user()
        if not user:
            print(f"[ACCEPT ORDER] ❌ No authenticated user - returning 401")
            return jsonify({'error': 'Unauthorized - Please login. Token missing or invalid.'}), 401
        
        print(f"[ACCEPT ORDER] User authenticated: {user.name} (ID: {user.id}, Role: {user.role}, Email: {user.email})")
        
        if user.role != 'owner':
            print(f"[ACCEPT ORDER] ❌ User {user.id} ({user.name}) has role '{user.role}' but needs 'owner'")
            print(f"[ACCEPT ORDER] User details: email={user.email}, role={user.role}")
            return jsonify({'error': f'Only owner can accept orders. Your role is: {user.role}'}), 403
        
        data = request.get_json() or {}
        is_vip = bool(data.get('is_vip', False))
        is_important = bool(data.get('is_important', False))
        
        print(f"[ACCEPT ORDER] Attempting to accept order ID: {order_id}")
        order = Order.query.get(order_id)
        
        if not order:
            print(f"[ACCEPT ORDER] Order {order_id} not found in database")
            return jsonify({'error': f'Order {order_id} not found'}), 404
        
        print(f"[ACCEPT ORDER] Order {order_id} found - Current status: {order.status}")
        
        # Allow accepting if status is 'pending' (relax the check slightly)
        if order.status != 'pending':
            print(f"[ACCEPT ORDER] Order {order_id} is not pending (current: {order.status})")
            # Still allow if already accepted (idempotent)
            if order.status == 'accepted':
                return jsonify({'success': True, 'order_id': order_id, 'message': 'Order already accepted'}), 200
            return jsonify({'error': f'Order status is {order.status}, cannot accept'}), 400
        
        # Update order status
        order.status = 'accepted'
        print(f"[ACCEPT ORDER] Updated order {order_id} status to 'accepted'")
        
        # Set VIP if requested
        if is_vip and order.user_id:
            user_obj = User.query.get(order.user_id)
            if user_obj:
                if not hasattr(user_obj, 'is_vip') or not user_obj.is_vip:
                    user_obj.is_vip = True
                    print(f"[ACCEPT ORDER] Marked user {user_obj.id} as VIP")
        
        # Add important note if requested
        if is_important:
            if order.kitchen_notes:
                if '[IMPORTANT]' not in order.kitchen_notes:
                    order.kitchen_notes = order.kitchen_notes + ' [IMPORTANT]'
            else:
                order.kitchen_notes = '[IMPORTANT]'
            print(f"[ACCEPT ORDER] Added IMPORTANT flag to order {order_id}")
        
        # Commit the order status change first
        db.session.commit()
        print(f"[ACCEPT ORDER] ✅ Order {order_id} accepted successfully")
        
        # Notify customer (separate try-catch to not affect main commit)
        try:
            from models import Notification
            notification = Notification(user_id=order.user_id, message=f"Your order {order.order_id} was accepted.")
            db.session.add(notification)
            db.session.commit()
            print(f"[ACCEPT ORDER] Notification sent to user {order.user_id}")
        except Exception as e:
            print(f"[ACCEPT ORDER] Failed to create notification: {e}")
            # Don't rollback here - order is already accepted
        
        export_csv()
        return jsonify({
            'success': True, 
            'order_id': order_id, 
            'order_db_id': order.id,
            'message': 'Order accepted and sent to kitchen queue'
        }), 200
    except Exception as e:
        db.session.rollback()
        print(f"[ACCEPT ORDER] ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ==================== APP PAYMENT SIMULATION ====================
@app.route('/api/orders/<order_id>/pay', methods=['POST', 'OPTIONS'])
def simulate_app_payment(order_id):
    """Simulate payment for mobile app orders"""
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        user = get_auth_user()
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401

        # The order_id here usually refers to the database ID (int), 
        # but let's handle both int ID and string order_id just in case
        order = Order.query.filter(
            (Order.id == order_id) | (Order.order_id == str(order_id))
        ).first()

        if not order:
            return jsonify({'error': 'Order not found'}), 404
            
        if order.user_id != user.id:
            return jsonify({'error': 'Unauthorized access to order'}), 403
            
        if order.status != 'pending':
            return jsonify({'message': f'Order is already {order.status}', 'success': True}), 200

        # Simulate successful payment
        order.status = 'paid' # Or 'accepted' if you want it to jump straight to kitchen
        # For this system, 'paid' might not be a valid status if the flow is pending -> accepted. 
        # Let's check the flow. 
        # Admin portal looks for 'pending'. 
        # If we set to 'paid', does it disappear from 'pending'? Yes.
        # But usually 'paid' implies it's ready for kitchen. 
        # Let's see... Web payment sets it to 'paid' (in demo_pay_confirm), 
        # wait, demo_pay_confirm updates `demo_payments` dict, NOT the Order table directly? 
        # Actually demo_pay_confirm is for the landing page demo.
        # Real orders: The `create_order` sets status='pending'.
        # Then Owner accepts it -> 'accepted'. 
        # Then Kitchen prepares -> 'preparing'.
        
        # If the app simulates "Online Payment", it should probably stay 'pending' 
        # but maybe with a transaction ID marked as paid?
        # OR, if "Online Payment" is successful, maybe it auto-accepts?
        # Let's just update transaction_id to show it was paid online 
        # and keep status 'pending' creates less friction for the existing Admin flow.
        
        # ACTUALLY: The user wants to "checkout demo payment in customer portal".
        # In the web customer portal, when you pay, does it auto-accept?
        # Usually online payment orders are still 'pending' acceptance by restaurant.
        
        # Let's set transaction_id to a simulated one and keep status 'pending'
        # UNLESS the user explicitly wants strictly "Paid" state. 
        # Most simple standard: Mark as pending, but PAID transaction.
        
        order.transaction_id = f"PAY-{uuid.uuid4().hex[:8].upper()}"
        # We can simulate 'online' payment method in daily log if we had one here, 
        # but for Order table, we just update transaction_id.
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Payment successful',
            'transaction_id': order.transaction_id,
            'status': order.status
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/owner/orders/<int:order_id>/reject', methods=['PUT', 'OPTIONS'])
def owner_reject_order(order_id):
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        order = Order.query.get(order_id)
        if not order or order.status not in ['pending','accepted']:
            return jsonify({'error': 'Order not found or cannot be rejected'}), 404
        
        # If order was paid online (not CASH), add amount to customer's wallet
        if order.user_id and order.transaction_id and order.transaction_id != 'CASH' and order.transaction_id != 'OFFLINE':
            customer = User.query.get(order.user_id)
            if customer:
                # Add wallet_balance field if it doesn't exist
                if not hasattr(customer, 'wallet_balance'):
                    customer.wallet_balance = 0.0
                customer.wallet_balance = (customer.wallet_balance or 0.0) + float(order.total_amount)
                print(f"Added ₹{order.total_amount} to wallet for user {customer.id} (Order {order.order_id} rejected)")
        
        order.status = 'rejected'
        db.session.commit()
        
        # Send notification to customer about refund
        try:
            from models import Notification
            if order.user_id:
                refund_msg = f"Your order {order.order_id} was rejected. "
                if order.transaction_id and order.transaction_id != 'CASH':
                    refund_msg += f"₹{order.total_amount} has been added to your wallet."
                notification = Notification(user_id=order.user_id, message=refund_msg)
                db.session.add(notification)
                db.session.commit()
        except Exception as e:
            print(f"Failed to send notification: {e}")
        
        export_csv()
        return jsonify({'success': True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/kitchen/orders/<int:order_id>/deliver', methods=['PUT', 'OPTIONS'])
def kitchen_deliver_order(order_id):
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user or user.role not in ['kitchen','owner']:
            return jsonify({'error': 'Unauthorized'}), 401
        order = Order.query.get(order_id)
        if not order:
            return jsonify({'error': 'Order not found'}), 404
        order.status = 'delivered'
        for c in order.coupons:
            c.status = 'completed'
            c.expired = True
            c.expired_at = datetime.utcnow()
        db.session.commit()
        export_csv()
        # Create simple notification row if model exists
        try:
            from models import Notification
            note = Notification(user_id=order.user_id, message=f"Your order {order.order_id} has been delivered. Thank you!")
            db.session.add(note)
            db.session.commit()
        except Exception:
            pass
        return jsonify({'success': True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/notifications', methods=['GET', 'OPTIONS'])
def api_notifications():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401
        try:
            from models import Notification
            notes = Notification.query.filter_by(user_id=user.id).order_by(Notification.created_at.desc()).limit(20).all()
            return jsonify([{'id':n.id,'message':n.message,'created_at':n.created_at.isoformat(),'is_read':n.is_read} for n in notes])
        except Exception:
            return jsonify([])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/user/profile', methods=['GET', 'OPTIONS'])
def api_user_profile():
    if request.method == 'OPTIONS':
        return '', 204
    """Get current user's profile information"""
    try:
        user = get_auth_user()
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Fetch fresh user data from database using the authenticated user's ID
        authenticated_user_id = user.id
        user = User.query.get(authenticated_user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Verify this is a customer (for customer profile page)
        # But allow any role to view their own profile
        created_at_str = ''
        try:
            if hasattr(user, 'created_at') and user.created_at:
                created_at_str = user.created_at.isoformat()
        except Exception:
            pass
        
        profile_data = {
            'id': user.id,
            'name': user.name or '',
            'email': user.email or '',
            'role': user.role or '',
            'phone': user.phone or '',
            'college_id': user.college_id or '',
            'department': user.department or '',
            'year': user.year or '',
            'address': user.address or '',
            'is_vip': getattr(user, 'is_vip', False),
            'wallet_balance': float(getattr(user, 'wallet_balance', 0.0) or 0.0),
            'created_at': created_at_str
        }
        
        return jsonify({
            'success': True,
            'user': profile_data
        }), 200
    except Exception as e:
        print(f"Profile Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ==================== WALLET API ENDPOINTS ====================
@app.route('/api/user/wallet', methods=['GET', 'OPTIONS'])
def get_wallet_balance():
    """Get current user's wallet balance"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Fetch fresh user data
        user = User.query.get(user.id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        balance = float(getattr(user, 'wallet_balance', 0.0) or 0.0)
        
        return jsonify({
            'success': True,
            'wallet_balance': balance
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/feedback', methods=['POST', 'OPTIONS'])
def api_feedback():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Verify user is customer
        if user.role != 'customer':
            return jsonify({'error': 'Only customers can submit feedback'}), 403
        
        data = request.get_json() or {}
        msg = (data.get('message') or '').strip()
        rating = data.get('rating')
        category = data.get('category', 'general')
        
        if not msg or len(msg.strip()) < 10:
            return jsonify({'error': 'Message is required and must be at least 10 characters'}), 400
        
        try:
            from models import Feedback
            # Parse rating safely
            rating_value = None
            if rating is not None:
                try:
                    rating_int = int(rating) if isinstance(rating, (int, float)) else int(str(rating).strip())
                    if 1 <= rating_int <= 5:
                        rating_value = rating_int
                except (ValueError, TypeError):
                    rating_value = None
            
            fb = Feedback(
                user_id=user.id, 
                message=msg, 
                rating=rating_value
            )
            db.session.add(fb)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Feedback submitted successfully'}), 201
        except Exception as e:
            db.session.rollback()
            print(f"Feedback submission error: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Failed to submit feedback: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/feedback/my', methods=['GET', 'OPTIONS'])
def get_my_feedback():
    if request.method == 'OPTIONS':
        return '', 204
    """Get current customer's feedback history"""
    try:
        user = get_auth_user()
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401
        
        if user.role != 'customer':
            return jsonify({'error': 'Only customers can view their feedback'}), 403
        
        from models import Feedback
        feedback_list = Feedback.query.filter_by(user_id=user.id).order_by(Feedback.created_at.desc()).limit(20).all()
        
        result = []
        for fb in feedback_list:
            result.append({
                'id': fb.id,
                'message': fb.message,
                'rating': fb.rating,
                'created_at': fb.created_at.isoformat() if fb.created_at else None
            })
        
        return jsonify({
            'success': True,
            'feedback': result
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/owner/dashboard-stats', methods=['GET', 'OPTIONS'])
def owner_dashboard_stats():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        today = date.today()
        yesterday = today - timedelta(days=1)
        # Include all orders (cash, online, delivered, accepted) - exclude only rejected/cancelled
        today_rev = db.session.query(func.sum(Order.total_amount)).filter(
            func.date(Order.created_at)==today,
            Order.status.notin_(['rejected', 'cancelled'])
        ).scalar() or 0.0
        yesterday_rev = db.session.query(func.sum(Order.total_amount)).filter(
            func.date(Order.created_at)==yesterday,
            Order.status.notin_(['rejected', 'cancelled'])
        ).scalar() or 0.0
        total_orders = Order.query.filter(
            func.date(Order.created_at)==today,
            Order.status.notin_(['rejected', 'cancelled'])
        ).count()
        try:
            from models import Feedback
            today_fb = db.session.query(func.avg(Feedback.rating)).filter(func.date(Feedback.created_at)==today).scalar()
            avg_rating = float(today_fb) if today_fb else None
        except Exception:
            avg_rating = None
        top_dish_query = db.session.query(MenuItem.name, MenuItem.icon, func.sum(OrderItem.quantity).label('qty')).join(OrderItem).join(Order).filter(func.date(Order.created_at)==today).group_by(MenuItem.id).order_by(desc('qty')).first()
        top_dish = top_dish_query.name if top_dish_query else '—'
        top_dish_icon = top_dish_query.icon if top_dish_query else ''
        return jsonify({'today_revenue': float(today_rev), 'yesterday_revenue': float(yesterday_rev), 'total_orders': total_orders, 'avg_rating': avg_rating, 'top_dish': top_dish, 'top_dish_icon': top_dish_icon}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/owner/feedback', methods=['GET', 'OPTIONS'])
def owner_get_feedback():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        from models import Feedback
        fb = Feedback.query.order_by(Feedback.created_at.desc()).limit(50).all()
        return jsonify([{'id': f.id, 'message': f.message, 'rating': f.rating, 'user_id': f.user_id, 'created_at': f.created_at.isoformat() if f.created_at else None} for f in fb]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/owner/orders/payment-status', methods=['GET', 'OPTIONS'])
def owner_payment_status():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        orders = Order.query.order_by(Order.created_at.desc()).limit(100).all()
        return jsonify([{'order_id': o.order_id, 'total': o.total_amount, 'transaction_id': o.transaction_id, 'status': o.status, 'payment_status': 'PAID' if o.transaction_id and o.transaction_id!='OFFLINE' and o.transaction_id!='CASH' else ('CASH' if o.transaction_id=='CASH' else 'PENDING'), 'created_at': o.created_at.isoformat() if o.created_at else None} for o in orders]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== OWNER: MENU AVAILABILITY & CASH ORDERS ====================
@app.route('/api/owner/menu/<int:item_id>/availability', methods=['PUT', 'OPTIONS'])
def owner_set_menu_availability(item_id):
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        data = request.get_json() or {}
        available = bool(data.get('available', True))
        item = MenuItem.query.get(item_id)
        if not item:
            return jsonify({'error': 'Menu item not found'}), 404
        item.available = available
        db.session.commit()
        return jsonify({'success': True, 'id': item_id, 'available': available}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ==================== IMAGE UPLOAD ENDPOINT ====================
@app.route('/api/upload/image', methods=['POST', 'OPTIONS'])
def upload_image():
    """Upload image for menu items (owner only)"""
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized - Owner access required'}), 401
        
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Check file extension
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        filename = file.filename.lower()
        if '.' not in filename or filename.rsplit('.', 1)[1] not in allowed_extensions:
            return jsonify({'error': 'Invalid file type. Allowed: PNG, JPG, JPEG, GIF, WEBP'}), 400
        
        # Create upload directory if it doesn't exist
        upload_folder = os.path.join('static', 'images', 'menu')
        os.makedirs(upload_folder, exist_ok=True)
        
        # Generate unique filename
        import uuid
        file_ext = filename.rsplit('.', 1)[1]
        unique_filename = f"{uuid.uuid4().hex[:12]}.{file_ext}"
        filepath = os.path.join(upload_folder, unique_filename)
        
        # Save file
        file.save(filepath)
        
        # Return URL
        image_url = f"/static/images/menu/{unique_filename}"
        
        return jsonify({
            'success': True,
            'image_url': image_url,
            'filename': unique_filename
        }), 200
        
    except Exception as e:
        print(f"Image Upload Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ==================== OWNER: ADD NEW DISH ====================
@app.route('/api/owner/menu/add', methods=['POST', 'OPTIONS'])
def owner_add_dish():
    """Add new dish to menu (owner only)"""
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized - Owner access required'}), 401
        
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        price = data.get('price', 0)
        description = data.get('description', '').strip()
        category = data.get('category', 'Other').strip()
        icon = data.get('icon', '🍽️')
        image_url = data.get('image_url', '').strip()
        tags = data.get('tags', '').strip()
        available = bool(data.get('available', True))
        
        if not name or price <= 0:
            return jsonify({'error': 'Name and price are required'}), 400
        
        # Create new menu item
        menu_item = MenuItem(
            name=name,
            icon=icon,
            price=float(price),
            description=description or name,
            category=category,
            available=available,
            tags=tags,
            image_url=image_url
        )
        
        db.session.add(menu_item)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'item': {
                'id': menu_item.id,
                'name': menu_item.name,
                'price': menu_item.price,
                'image_url': menu_item.image_url or ''
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        print(f"Add Dish Error: {e}")
        return jsonify({'error': str(e)}), 500

# ==================== OFFER MANAGEMENT ====================
@app.route('/api/offers/active', methods=['GET', 'OPTIONS'])
def get_active_offer():
    """Get currently active offer"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        active_offer = Offer.query.filter(
            Offer.is_active == True,
            Offer.start_date <= datetime.utcnow(),
            or_(Offer.end_date.is_(None), Offer.end_date >= datetime.utcnow())
        ).order_by(Offer.created_at.desc()).first()
        
        if not active_offer:
            return jsonify({'active': False}), 200
        
        return jsonify({
            'active': True,
            'offer': {
                'id': active_offer.id,
                'name': active_offer.name,
                'description': active_offer.description,
                'discount_percent': active_offer.discount_percent,
                'start_date': active_offer.start_date.isoformat() if active_offer.start_date else None,
                'end_date': active_offer.end_date.isoformat() if active_offer.end_date else None
            }
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/owner/offers', methods=['GET', 'OPTIONS'])
def owner_list_offers():
    """List all offers (owner only)"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        offers = Offer.query.order_by(Offer.created_at.desc()).all()
        return jsonify([{
            'id': o.id,
            'name': o.name,
            'description': o.description,
            'discount_percent': o.discount_percent,
            'start_date': o.start_date.isoformat() if o.start_date else None,
            'end_date': o.end_date.isoformat() if o.end_date else None,
            'is_active': o.is_active
        } for o in offers]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/owner/offers', methods=['POST', 'OPTIONS'])
def owner_create_offer():
    """Create new offer (owner only)"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        discount_percent = float(data.get('discount_percent', 0))
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')  # Can be None
        
        if not name or discount_percent <= 0:
            return jsonify({'error': 'Name and discount percent are required'}), 400
        
        # Deactivate all existing offers
        existing_offers = Offer.query.filter(Offer.is_active == True).all()
        for offer in existing_offers:
            offer.is_active = False
        db.session.commit()
        
        start_date = datetime.utcnow()
        if start_date_str:
            try:
                start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
            except:
                pass
        
        end_date = None
        if end_date_str:
            try:
                end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
            except:
                pass
        
        offer = Offer(
            name=name,
            description=data.get('description', '').strip(),
            discount_percent=discount_percent,
            start_date=start_date,
            end_date=end_date,
            is_active=True,
            created_by=user.id
        )
        db.session.add(offer)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'offer': {
                'id': offer.id,
                'name': offer.name,
                'discount_percent': offer.discount_percent
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/owner/offers/<int:offer_id>', methods=['PUT', 'OPTIONS'])
def owner_update_offer(offer_id):
    """Update offer (owner only)"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        offer = Offer.query.get(offer_id)
        if not offer:
            return jsonify({'error': 'Offer not found'}), 404
        
        data = request.get_json() or {}
        if 'name' in data:
            offer.name = data['name'].strip()
        if 'description' in data:
            offer.description = data['description'].strip()
        if 'discount_percent' in data:
            offer.discount_percent = float(data['discount_percent'])
        if 'is_active' in data:
            offer.is_active = bool(data['is_active'])
        if 'start_date' in data:
            try:
                offer.start_date = datetime.fromisoformat(data['start_date'].replace('Z', '+00:00'))
            except:
                pass
        if 'end_date' in data:
            if data['end_date']:
                try:
                    offer.end_date = datetime.fromisoformat(data['end_date'].replace('Z', '+00:00'))
                except:
                    pass
            else:
                offer.end_date = None
        
        db.session.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/owner/offers/<int:offer_id>', methods=['DELETE', 'OPTIONS'])
def owner_delete_offer(offer_id):
    """Delete offer (owner only)"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        offer = Offer.query.get(offer_id)
        if not offer:
            return jsonify({'error': 'Offer not found'}), 404
        
        db.session.delete(offer)
        db.session.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ==================== COMBO MANAGEMENT ====================
@app.route('/api/combos', methods=['GET', 'OPTIONS'])
def list_combos():
    """List all available combos"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        combos = Combo.query.filter_by(available=True).all()
        result = []
        for combo in combos:
            items = []
            for combo_item in combo.items:
                items.append({
                    'id': combo_item.menu_item.id,
                    'name': combo_item.menu_item.name,
                    'icon': combo_item.menu_item.icon,
                    'quantity': combo_item.quantity
                })
            result.append({
                'id': combo.id,
                'name': combo.name,
                'description': combo.description,
                'price': combo.price,
                'icon': combo.icon,
                'image_url': combo.image_url or '',
                'items': items
            })
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/owner/combos', methods=['GET', 'OPTIONS'])
def owner_list_combos():
    """List all combos (owner only, includes unavailable)"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        combos = Combo.query.all()
        result = []
        for combo in combos:
            items = []
            for combo_item in combo.items:
                items.append({
                    'id': combo_item.menu_item.id,
                    'name': combo_item.menu_item.name,
                    'icon': combo_item.menu_item.icon,
                    'quantity': combo_item.quantity
                })
            result.append({
                'id': combo.id,
                'name': combo.name,
                'description': combo.description,
                'price': combo.price,
                'icon': combo.icon,
                'available': combo.available,
                'image_url': combo.image_url or '',
                'items': items
            })
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/owner/combos', methods=['POST', 'OPTIONS'])
def owner_create_combo():
    """Create new combo (owner only)"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        price = float(data.get('price', 0))
        items = data.get('items', [])  # Array of {menu_item_id, quantity}
        
        if not name or price <= 0 or not items:
            return jsonify({'error': 'Name, price, and items are required'}), 400
        
        combo = Combo(
            name=name,
            description=data.get('description', '').strip(),
            price=price,
            icon=data.get('icon', '🍱'),
            available=bool(data.get('available', True)),
            image_url=data.get('image_url', '').strip() or None
        )
        db.session.add(combo)
        db.session.flush()
        
        for item_data in items:
            menu_item_id = int(item_data.get('menu_item_id'))
            quantity = int(item_data.get('quantity', 1))
            combo_item = ComboItem(
                combo_id=combo.id,
                menu_item_id=menu_item_id,
                quantity=quantity
            )
            db.session.add(combo_item)
        
        db.session.commit()
        
        return jsonify({'success': True, 'combo_id': combo.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/owner/combos/<int:combo_id>', methods=['PUT', 'OPTIONS'])
def owner_update_combo(combo_id):
    """Update combo (owner only)"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        combo = Combo.query.get(combo_id)
        if not combo:
            return jsonify({'error': 'Combo not found'}), 404
        
        data = request.get_json() or {}
        if 'name' in data:
            combo.name = data['name'].strip()
        if 'description' in data:
            combo.description = data['description'].strip()
        if 'price' in data:
            combo.price = float(data['price'])
        if 'icon' in data:
            combo.icon = data['icon']
        if 'available' in data:
            combo.available = bool(data['available'])
        if 'image_url' in data:
            combo.image_url = data['image_url'].strip() if data['image_url'] else None
        if 'items' in data:
            # Delete existing items
            ComboItem.query.filter_by(combo_id=combo.id).delete()
            # Add new items
            for item_data in data['items']:
                combo_item = ComboItem(
                    combo_id=combo.id,
                    menu_item_id=int(item_data.get('menu_item_id')),
                    quantity=int(item_data.get('quantity', 1))
                )
                db.session.add(combo_item)
        
        db.session.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/owner/combos/<int:combo_id>', methods=['DELETE', 'OPTIONS'])
def owner_delete_combo(combo_id):
    """Delete combo (owner only)"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        combo = Combo.query.get(combo_id)
        if not combo:
            return jsonify({'error': 'Combo not found'}), 404
        
        db.session.delete(combo)
        db.session.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ==================== DAILY ORDER LOGS ====================
@app.route('/api/owner/daily-orders', methods=['GET', 'OPTIONS'])
def owner_daily_orders():
    """Get all orders for a specific day (owner only)"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        
        target_date_str = request.args.get('date', date.today().isoformat())
        try:
            target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        except:
            target_date = date.today()
        
        logs = DailyOrderLog.query.filter_by(order_date=target_date).order_by(DailyOrderLog.order_time.desc()).all()
        
        result = []
        for log in logs:
            items = []
            try:
                items = json.loads(log.items_json) if log.items_json else []
            except:
                pass
            
            result.append({
                'id': log.id,
                'order_id': log.order_id,
                'customer_name': log.customer_name,
                'customer_phone': log.customer_phone,
                'customer_email': log.customer_email,
                'order_date': log.order_date.isoformat() if log.order_date else None,
                'order_time': log.order_time.isoformat() if log.order_time else None,
                'total_amount': log.total_amount,
                'transaction_id': log.transaction_id,
                'payment_method': log.payment_method,
                'status': log.status,
                'items': items
            })
        
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/owner/orders/create-cash', methods=['POST', 'OPTIONS'])
def owner_create_cash_order():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user or user.role != 'owner':
            return jsonify({'error': 'Unauthorized'}), 401
        data = request.get_json() or {}
        items = data.get('items', [])
        if not items:
            return jsonify({'error': 'No items'}), 400
        # Compute total from DB prices for safety
        total = 0.0
        # Generate unique order ID using timestamp + random suffix
        import random
        order_id = f"ORD{int(datetime.utcnow().timestamp())}{random.randint(100,999)}"
        # Ensure uniqueness
        while Order.query.filter_by(order_id=order_id).first():
            order_id = f"ORD{int(datetime.utcnow().timestamp())}{random.randint(100,999)}"
        # For cash orders, user_id must be set (NOT NULL constraint)
        # We'll use owner's ID since owner is placing the order for walk-in customer
        order = Order(
            order_id=order_id,
            user_id=user.id,  # Use owner's ID for cash orders (database requires NOT NULL)
            customer_name=data.get('customer_name', 'Walk-in Customer'),
            customer_phone=data.get('customer_phone', '0000000000'),
            total_amount=0.0,
            transaction_id='CASH',
            status='accepted'
        )
        db.session.add(order)
        db.session.flush()
        for it in items:
            menu_item = MenuItem.query.get(int(it.get('id')))
            qty = int(it.get('quantity', 1))
            if menu_item and qty > 0:
                total += (menu_item.price or 0.0) * qty
                db.session.add(OrderItem(order_id=order.id, menu_item_id=menu_item.id, quantity=qty, price=menu_item.price))
        order.total_amount = float(total)
        db.session.flush()
        
        # Log to DailyOrderLog for cash orders
        try:
            order_date = datetime.utcnow().date()
            order_time = datetime.utcnow()
            order_items_data = []
            for it in items:
                menu_item = MenuItem.query.get(int(it.get('id')))
                if menu_item:
                    order_items_data.append({
                        'id': menu_item.id,
                        'name': menu_item.name,
                        'icon': menu_item.icon,
                        'quantity': int(it.get('quantity', 1)),
                        'price': menu_item.price
                    })
            
            daily_log = DailyOrderLog(
                order_id=order.order_id,
                order_db_id=order.id,
                user_id=user.id,  # Use owner's ID for cash orders (database requires NOT NULL)
                customer_name=order.customer_name,
                customer_phone=order.customer_phone,
                customer_email='',  # Cash orders don't have email
                order_date=order_date,
                order_time=order_time,
                total_amount=order.total_amount,
                transaction_id='CASH',
                payment_method='cash',
                status='accepted',
                items_json=json.dumps(order_items_data)
            )
            db.session.add(daily_log)
        except Exception as e:
            print(f"Error creating daily log for cash order: {e}")
        
        db.session.commit()
        export_csv()
        return jsonify({'success': True, 'order_id': order.order_id, 'total': total}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ==================== KITCHEN: STATUS UPDATES & LIVE FEED ====================
@app.route('/api/kitchen/orders/<int:order_id>/status', methods=['PUT', 'OPTIONS'])
def kitchen_update_status(order_id):
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user or user.role not in ['kitchen', 'owner']:
            return jsonify({'error': 'Unauthorized'}), 401
        data = request.get_json() or {}
        status = str(data.get('status', '')).lower()
        if status not in ['preparing','ready','delivered','accepted','rejected','pending']:
            return jsonify({'error': 'Invalid status'}), 400
        order = Order.query.get(order_id)
        if not order:
            return jsonify({'error': 'Order not found'}), 404
        order.status = status
        ts = datetime.utcnow()
        if status == 'preparing':
            order.preparation_started_at = order.preparation_started_at or ts
        if status == 'ready':
            order.preparation_completed_at = ts
            try:
                from models import Notification
                db.session.add(Notification(user_id=order.user_id, message=f"Your order {order.order_id} is ready for pickup."))
            except Exception:
                pass
        if status == 'delivered':
            for c in order.coupons:
                c.status = 'completed'
                c.expired = True
                c.expired_at = ts
            try:
                from models import Notification
                db.session.add(Notification(user_id=order.user_id, message=f"Your order {order.order_id} has been delivered. Thank you!"))
            except Exception:
                pass
        db.session.commit()
        export_csv()
        return jsonify({'success': True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/kitchen/orders/live', methods=['GET', 'OPTIONS'])
def kitchen_live_orders():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user or user.role not in ['kitchen','owner']:
            return jsonify({'error': 'Unauthorized'}), 401
        orders = Order.query.filter(Order.status.in_(['pending','accepted','preparing','ready'])).order_by(Order.created_at.desc()).all()
        return jsonify([serialize_order(o) for o in orders]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/kitchen/orders/by-code/<order_code>/deliver', methods=['PUT', 'OPTIONS'])
def kitchen_deliver_by_code(order_code):
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user or user.role not in ['kitchen','owner']:
            return jsonify({'error': 'Unauthorized'}), 401
        order = Order.query.filter_by(order_id=order_code).first()
        if not order:
            return jsonify({'error': 'Order not found'}), 404
        order.status = 'delivered'
        ts = datetime.utcnow()
        for c in order.coupons:
            c.status = 'completed'
            c.expired = True
            c.expired_at = ts
        try:
            from models import Notification
            db.session.add(Notification(user_id=order.user_id, message=f"Your order {order.order_id} has been delivered. Thank you!"))
        except Exception:
            pass
        db.session.commit()
        export_csv()
        return jsonify({'success': True}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/kitchen/orders/history', methods=['GET', 'OPTIONS'])
def kitchen_order_history():
    """Get order history for kitchen staff with optional filters"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user:
            print(f"[KITCHEN HISTORY] No user found - auth failed")
            return jsonify({'error': 'Unauthorized - Please login'}), 401
        
        if user.role not in ['kitchen', 'owner']:
            print(f"[KITCHEN HISTORY] Role mismatch - expected 'kitchen' or 'owner', got '{user.role}'")
            return jsonify({'error': f'Unauthorized - Kitchen/Owner access required. Your role is: {user.role}'}), 403
        
        status_filter = request.args.get('status', '').strip()
        date_filter = request.args.get('date', '').strip()
        
        # Base query - all orders (not just live ones)
        query = Order.query
        
        # Filter by status if provided
        if status_filter:
            query = query.filter(Order.status == status_filter.lower())
        
        # Filter by date if provided
        if date_filter:
            try:
                filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
                query = query.filter(db.cast(Order.created_at, db.Date) == filter_date)
            except ValueError:
                pass
        
        # Order by most recent first
        orders = query.order_by(Order.created_at.desc()).limit(500).all()
        
        return jsonify([serialize_order(o) for o in orders]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/owner/orders/history', methods=['GET', 'OPTIONS'])
def owner_order_history():
    """Get order history for owner with optional filters"""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        user = get_auth_user()
        if not user:
            print(f"[OWNER HISTORY] No user found - auth failed")
            return jsonify({'error': 'Unauthorized - Please login'}), 401
        
        print(f"[OWNER HISTORY] User: {user.name}, Role: {user.role}")
        
        if user.role != 'owner':
            print(f"[OWNER HISTORY] Role mismatch - expected 'owner', got '{user.role}'")
            return jsonify({'error': f'Unauthorized - Owner access required. Your role is: {user.role}'}), 403
        
        status_filter = request.args.get('status', '').strip()
        date_filter = request.args.get('date', '').strip()
        payment_filter = request.args.get('payment', '').strip()
        
        # Base query - all orders
        query = Order.query
        
        # Filter by status if provided
        if status_filter:
            query = query.filter(Order.status == status_filter.lower())
        
        # Filter by date if provided
        if date_filter:
            try:
                filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
                query = query.filter(db.cast(Order.created_at, db.Date) == filter_date)
            except ValueError:
                pass
        
        # Filter by payment status if provided
        if payment_filter:
            if payment_filter.upper() == 'PAID':
                query = query.filter(Order.transaction_id != 'CASH', Order.transaction_id != 'PENDING', Order.transaction_id != '')
            elif payment_filter.upper() == 'CASH':
                query = query.filter(Order.transaction_id == 'CASH')
            elif payment_filter.upper() == 'PENDING':
                query = query.filter(or_(Order.transaction_id.in_(['', 'PENDING']), Order.transaction_id.is_(None)))
        
        # Order by most recent first
        orders = query.order_by(Order.created_at.desc()).limit(1000).all()
        
        # Serialize with additional payment info
        result = []
        for o in orders:
            order_data = serialize_order(o)
            # Add payment status
            if o.transaction_id == 'CASH':
                order_data['payment_status'] = 'CASH'
            elif o.transaction_id and o.transaction_id not in ['', 'PENDING']:
                order_data['payment_status'] = 'PAID'
            else:
                order_data['payment_status'] = 'PENDING'
            result.append(order_data)
        
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def export_csv():
    try:
        # users.csv
        with open('users.csv','w',newline='',encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['id','name','email','phone','college_id','role'])
            for u in User.query.all():
                w.writerow([u.id,u.name,u.email,u.phone,u.college_id,u.role])
        # orders.csv
        with open('orders.csv','w',newline='',encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['id','order_id','user_id','total','status','created_at'])
            for o in Order.query.order_by(Order.created_at.desc()).all():
                w.writerow([o.id,o.order_id,o.user_id,o.total_amount,o.status,o.created_at.isoformat()])
    except Exception:
        pass

# ==================== NEW ROUTES: KITCHEN PORTAL ====================

KITCHEN_HTML = """
<!DOCTYPE html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Kitchen Portal</title>
<link rel='preconnect' href='https://fonts.googleapis.com'><style>body{font-family:Segoe UI,Tahoma,Arial;margin:0;background:#0f172a;color:#e2e8f0} .top{display:flex;justify-content:space-between;align-items:center;padding:16px 20px;background:#111827;position:sticky;top:0} .status{display:inline-block;padding:6px 10px;border-radius:999px;font-size:.8em;margin-right:8px} .pending{background:#f59e0b;color:#111827} .preparing{background:#3b82f6} .ready{background:#22c55e} .rejected{background:#ef4444} .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;padding:16px} .card{background:#111827;border-radius:12px;padding:12px;border:1px solid #1f2937} button{padding:8px 10px;border:none;border-radius:8px;background:#374151;color:#e5e7eb;margin:4px;cursor:pointer} button.primary{background:#3b82f6} button.warn{background:#f59e0b} button.danger{background:#ef4444} .metrics{display:flex;gap:12px;padding:0 16px 12px} .metric{flex:1;background:#111827;border:1px solid #1f2937;border-radius:12px;padding:12px;text-align:center}
</style></head><body>
<div class='top'><div><strong>🍳 Kitchen Portal</strong></div><div><button onclick="location.reload()">Refresh</button></div></div>
<div class='metrics'><div class='metric'><div id='m_completed' style='font-size:1.4em'>0</div><div>Completed Today</div></div><div class='metric'><div id='m_avg' style='font-size:1.4em'>--</div><div>Avg Prep Time</div></div></div>
<div style='padding:0 16px 8px'><select id='filter' onchange='load()'><option value='all'>All</option><option value='pending'>Pending</option><option value='preparing'>Preparing</option><option value='ready'>Ready</option></select></div>
<div id='wrap' class='grid'></div>
<audio id='ping' src='https://actions.google.com/sounds/v1/alarms/beep_short.ogg' preload='auto'></audio>
<script>
const API = location.origin + '/api';
let lastCount = 0;
async function load(){
  const q = await fetch(API + '/orders/my-orders', {headers:{'Authorization': localStorage.getItem('authToken')?'Bearer '+localStorage.getItem('authToken'):''}});
  let data = []; try{ data = await q.json(); }catch(e){}
  const f = document.getElementById('filter').value;
  const filtered = data.filter(o=> f==='all' ? true : o.status===f || o.status===('kitchen_'+f));
  const w = document.getElementById('wrap'); w.innerHTML='';
  filtered.forEach(o=>{
    const div=document.createElement('div');
    div.className='card';
    div.innerHTML = `<div style='display:flex;justify-content:space-between;align-items:center;'>
      <div><strong>#${o.id}</strong></div>
      <span class='status ${o.status.includes('pending')?'pending':(o.status.includes('preparing')?'preparing':(o.status.includes('ready')?'ready':'rejected'))}'>${o.status.toUpperCase()}</span>
    </div>
    <div style='color:#9ca3af;margin:6px 0'>${new Date(o.timestamp).toLocaleTimeString()}</div>
    <div>${o.items.map(i=>`${i.icon||''} ${i.name} x${i.quantity}`).join('<br>')}</div>
    <div style='margin-top:8px;display:flex;flex-wrap:wrap'>
      <button class='primary' onclick=upd('${o.id}','accepted')>Accept</button>
      <button class='warn' onclick=upd('${o.id}','preparing')>Preparing</button>
      <button class='primary' onclick=upd('${o.id}','ready')>Ready</button>
      <button class='danger' onclick=upd('${o.id}','rejected')>Reject</button>
    </div>`;
    w.appendChild(div);
  });
  if (data.length > lastCount){ try{document.getElementById('ping').play()}catch(e){} }
  lastCount = data.length;
}
async function upd(id, s){
  // Local-only status update on this MVP (for full sync, add a server PATCH route)
  localStorage.setItem('kitchen_update_'+id, s);
  load();
}
load(); setInterval(load, 5000);
</script></body></html>
"""

@app.route('/kitchen', methods=['GET'])
@role_required('kitchen', 'owner')
def kitchen_portal():
    return render_template_string(KITCHEN_HTML)

# ==================== NEW ROUTES: ADMIN PORTAL (MVP) ====================

ADMIN_HTML = """
<!DOCTYPE html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>Admin Portal</title>
<script src='https://cdn.jsdelivr.net/npm/chart.js'></script>
<style>body{font-family:Segoe UI,Tahoma,Arial;margin:0;background:#0b1020;color:#eaeef7} .top{padding:16px;background:#0f1530} .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;padding:16px} .card{background:#0f1530;border-radius:12px;padding:12px;border:1px solid #1b2348}</style></head>
<body><div class='top'><strong>📊 Admin Analytics</strong></div>
<div class='grid'>
  <div class='card'><canvas id='sales'></canvas></div>
  <div class='card'><canvas id='perhour'></canvas></div>
  <div class='card'><canvas id='top5'></canvas></div>
</div>
<script>
const API = location.origin + '/api';
async function fetchJSON(u){ try{ const r=await fetch(u,{headers:{'Authorization': localStorage.getItem('authToken')?'Bearer '+localStorage.getItem('authToken'):''}}); return await r.json(); }catch(e){return []}}
(async ()=>{
  // Top dishes (reuses existing analytics endpoint for today)
  const date = new Date().toISOString().split('T')[0];
  const top = await fetchJSON(API + '/orders/analytics?date='+date);
  const names = top.map(x=>x.name); const qty = top.map(x=>x.quantity);
  new Chart(document.getElementById('top5'),{type:'bar',data:{labels:names,datasets:[{label:'Qty',data:qty,backgroundColor:'#3b82f6'}]}});
  // Fake sales and per hour (MVP placeholders)
  new Chart(document.getElementById('sales'),{type:'doughnut',data:{labels:['Today','Yesterday'],datasets:[{data:[top.reduce((s,x)=>s+(x.revenue||0),0), Math.max(0, top.reduce((s,x)=>s+(x.revenue||0),0)-500)],backgroundColor:['#22c55e','#f59e0b']} ]}});
  new Chart(document.getElementById('perhour'),{type:'line',data:{labels:[...Array(8)].map((_,i)=>`${i*3}:00`),datasets:[{label:'Orders',data:[5,3,6,2,4,7,5,8],borderColor:'#a78bfa'}]}});
})();
</script></body></html>
"""

@app.route('/admin', methods=['GET'])
@role_required('owner')
def admin_portal():
    return render_template_string(ADMIN_HTML)
# ==================== INIT DATABASE ====================

def _run_column_migrations():
    """
    Safely add columns that exist in the SQLAlchemy models but may be
    missing from an already-deployed database (schema drift fix).
    Supabase PostgreSQL compatible — uses information_schema.columns with
    table_schema='public', double-quote identifiers, SMALLINT not TINYINT.
    Fully idempotent — safe to run on every startup.
    """
    migrations = [
        # table,    column,           DDL type (PostgreSQL compatible)
        ("user",    "firebase_uid",   "VARCHAR(128) DEFAULT NULL"),
        ("user",    "is_vip",         "SMALLINT NOT NULL DEFAULT 0"),
        ("user",    "is_blocked",     "SMALLINT NOT NULL DEFAULT 0"),
        ("user",    "wallet_balance", "FLOAT NOT NULL DEFAULT 0"),
        ("user",    "referred_by",    "INTEGER DEFAULT NULL"),
    ]
    engine = db.engine
    with engine.connect() as conn:
        for table, column, col_def in migrations:
            try:
                # PostgreSQL: check information_schema.columns with table_schema='public'
                check_sql = (
                    f"SELECT COUNT(*) FROM information_schema.columns "
                    f"WHERE table_schema = 'public' "
                    f"AND table_name = '{table}' "
                    f"AND column_name = '{column}'"
                )
                result = conn.execute(db.text(check_sql))
                exists = result.scalar()
                if not exists:
                    # PostgreSQL uses double-quotes for identifiers (not backticks)
                    conn.execute(db.text(
                        f'ALTER TABLE "{table}" ADD COLUMN "{column}" {col_def}'
                    ))
                    conn.commit()
                    print(f'✅ Migration: added column "{table}"."{column}"')
            except Exception as e:
                print(f'⚠️  Migration skipped for "{table}"."{column}": {e}')
    print("✅ Column migrations complete")


def init_db():
    with app.app_context():
        # Create all tables defined in models.py
        db.create_all()
        print("✅ Database tables created/verified")

        # ── Column migrations: add any columns that exist in the model
        #    but may be missing from an older database schema ──────────
        _run_column_migrations()
        
        # Add menu items if empty
        if MenuItem.query.count() == 0:
            items = [
                MenuItem(name="Chaha", icon="🍵", price=10.0, description="Hot tea", category="Beverages", tags="breakfast,tea", available=True, image_url="/static/images/menu/chaha.jpg"),
                MenuItem(name="Special Tea", icon="🍵", price=12.0, description="Special Ginger Tea", category="Beverages", tags="breakfast,tea", available=True, image_url="/static/images/menu/8b712d436b2f.jpg"),
                MenuItem(name="Butter paneer", icon="🥘", price=70.0, description="Rich spicy gravy", category="Lunch", tags="lunch,curry", available=True, image_url="/static/images/menu/9bbadaef053e.jpg"),
                MenuItem(name="Coffee", icon="☕", price=20.0, description="Hot Coffee", category="Beverages", tags="breakfast,coffee", available=True, image_url="/static/images/menu/bd51eb7e6ccf.jpg"),
                # Using the uploaded image for Vada Pav if available, else from backup
                MenuItem(name="Vadapav", icon="🍔", price=15.0, description="Mumbai Burger", category="Street Food", tags="snack", available=True, image_url="/static/images/menu/661c1ce82458.jpg"),
                MenuItem(name="Samosa", icon="🥟", price=20.0, description="Fried pastry with potato filling", category="Street Food", tags="snack", available=True, image_url="/static/images/menu/e0630da3aeb6.jpg"),
                MenuItem(name="Poha", icon="🍚", price=20.0, description="Flattened rice with spices", category="Breakfast", tags="breakfast", available=True, image_url="/static/images/menu/66ff81a07185.jpg"),
                MenuItem(name="Misal", icon="🍛", price=75.0, description="Spicy curry with sprouts", category="Lunch", tags="lunch,spicy", available=False, image_url=""),
                MenuItem(name="Paratha", icon="🫓", price=60.0, description="Stuffed flatbread", category="Lunch", tags="lunch", available=True, image_url="/static/images/menu/81ffdfa2ebfc.jpg"),
                MenuItem(name="Sandwich", icon="🥪", price=100.0, description="Grilled vegetable sandwich", category="Breakfast", tags="breakfast,snack", available=True, image_url="/static/images/menu/1cdcdf4c306c.jpg"),
                MenuItem(name="Cold Coffee", icon="🥤", price=30.0, description="Chilled milk coffee", category="Beverages", tags="beverage,cold", available=True, image_url="/static/images/menu/e0a890a7f55a.jpg"),
            ]
            for item in items:
                db.session.add(item)
            db.session.commit()
            print("✅ Menu items initialized")
        
        # Add test users if not present
        if not User.query.filter_by(phone="9999999999").first():
            test_customer = User(
                name="Test Customer",
                email="customer@test.com",
                phone="9999999999",
                college_id="CUST001",
                password=generate_password_hash("pass123"),
                role="customer",
                department="Computer Science",
                year="3rd Year",
                address="Pune, Maharashtra"
            )
            db.session.add(test_customer)
            print("✅ Test Customer created")

        # ── Owner account — credentials from .env ────────────────────────
        _owner_id  = os.environ.get('OWNER_COLLEGE_ID', 'MMCOE_OWNER_2025')
        _owner_pwd = os.environ.get('OWNER_PASSWORD',   'ChangeMe@Owner#1')
        if not User.query.filter_by(college_id=_owner_id).first():
            owner = User(
                name="Admin Owner",
                email="owner@mmcoe.edu",
                phone="0000000001",  # placeholder — staff don't need real phone
                college_id=_owner_id,
                password=generate_password_hash(_owner_pwd),
                role="owner",
                department="Management",
                year="Staff"
            )
            db.session.add(owner)
            print(f"✅ Owner account created (college_id: {_owner_id})")

        # ── Kitchen account — credentials from .env ───────────────────────
        _kitchen_id  = os.environ.get('KITCHEN_COLLEGE_ID', 'MMCOE_KITCHEN_2025')
        _kitchen_pwd = os.environ.get('KITCHEN_PASSWORD',   'ChangeMe@Kitchen#1')
        if not User.query.filter_by(college_id=_kitchen_id).first():
            kitchen = User(
                name="Kitchen Staff",
                email="kitchen@mmcoe.edu",
                phone="0000000002",  # placeholder — staff don't need real phone
                college_id=_kitchen_id,
                password=generate_password_hash(_kitchen_pwd),
                role="kitchen",
                department="Kitchen",
                year="Staff"
            )
            db.session.add(kitchen)
            print(f"✅ Kitchen account created (college_id: {_kitchen_id})")
            
        db.session.commit()

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    # Register blueprints
    from financial_reports import financial_reports_bp
    from customer_management import customer_management_bp
    from owner_analytics_dashboard import owner_analytics_bp
    from menu_pricing_management import menu_management_bp
    from inventory_management import inventory_bp
    from real_time_orders import kitchen_orders_bp
    from menu_availability import menu_availability_bp
    from kitchen_analytics import kitchen_analytics_bp

    app.register_blueprint(financial_reports_bp)
    app.register_blueprint(customer_management_bp)
    app.register_blueprint(owner_analytics_bp)
    app.register_blueprint(menu_management_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(kitchen_orders_bp)
    app.register_blueprint(menu_availability_bp)
    app.register_blueprint(kitchen_analytics_bp)
    
    # Register advanced features blueprint
    from advanced_features import advanced_features_bp
    app.register_blueprint(advanced_features_bp)
    
    # Register chatbot blueprint
    from chatbot_routes import chatbot_bp
    app.register_blueprint(chatbot_bp)
    

    print("\n" + "="*70)
    print("MMCOE SMART CANTEEN BACKEND SERVER")
    print("="*70)
    print("Server URL: http://localhost:5000")
    print("API Base: http://localhost:5000/api")
    print("CORS: Enabled for all origins")
    print("\nACCOUNTS:")
    print("   Customer: 9999999999 / pass123 (test only)")
    print("   Owner:    set via OWNER_COLLEGE_ID + OWNER_PASSWORD in .env")
    print("   Kitchen:  kitchen    / pass123")
    print("\nNOTES:")
    print("   - OTP is displayed in console (no email service required)")
    print("   - All endpoints support CORS")
    print("   - Database: Supabase PostgreSQL")
    print("="*70 + "\n")

print("Blueprints registered")
# Run server
app.run(debug=True, port=5000, host='0.0.0.0')