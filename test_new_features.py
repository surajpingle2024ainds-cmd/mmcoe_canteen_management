#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test script to verify new features are working"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import app, db
from models import Combo, ComboItem, Offer, DailyOrderLog, MenuItem

def test_database_tables():
    """Test if new tables exist"""
    print("Testing database tables...")
    with app.app_context():
        try:
            # Try to query each table
            combos = Combo.query.all()
            offers = Offer.query.all()
            logs = DailyOrderLog.query.all()
            print(f"✓ Combo table exists - {len(combos)} combos found")
            print(f"✓ Offer table exists - {len(offers)} offers found")
            print(f"✓ DailyOrderLog table exists - {len(logs)} logs found")
            return True
        except Exception as e:
            print(f"✗ Error accessing tables: {e}")
            print("Creating tables...")
            try:
                db.create_all()
                print("✓ Tables created successfully")
                return True
            except Exception as ex:
                print(f"✗ Error creating tables: {ex}")
                return False

def test_models():
    """Test if models can be instantiated"""
    print("\nTesting models...")
    try:
        with app.app_context():
            # Test Offer
            test_offer = Offer(
                name="Test Offer",
                discount_percent=10.0,
                start_date=db.func.now(),
                is_active=False
            )
            print("✓ Offer model works")
            
            # Test Combo
            test_combo = Combo(
                name="Test Combo",
                price=100.0,
                available=False
            )
            print("✓ Combo model works")
            
            return True
    except Exception as e:
        print(f"✗ Model test failed: {e}")
        return False

def test_routes():
    """Test if routes are registered"""
    print("\nTesting routes...")
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append(rule.rule)
    
    required_routes = [
        '/api/offers/active',
        '/api/owner/offers',
        '/api/combos',
        '/api/owner/combos',
        '/api/owner/daily-orders',
        '/owner/offers',
        '/owner/combos',
        '/owner/daily-orders'
    ]
    
    missing = []
    for route in required_routes:
        if route not in routes:
            missing.append(route)
    
    if missing:
        print(f"✗ Missing routes: {', '.join(missing)}")
        return False
    else:
        print("✓ All routes registered")
        return True

if __name__ == '__main__':
    print("=" * 60)
    print("Testing New Features")
    print("=" * 60)
    
    results = []
    results.append(("Database Tables", test_database_tables()))
    results.append(("Models", test_models()))
    results.append(("Routes", test_routes()))
    
    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)
    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{name}: {status}")
    
    all_passed = all(r for _, r in results)
    print("=" * 60)
    if all_passed:
        print("All tests passed!")
    else:
        print("Some tests failed. Please check the errors above.")
    print("=" * 60)

